"""LoRA fine-tune (SFT + DPO) for neighborhood agent tool-calling."""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TrainConfig:
    base_model: str = "Qwen/Qwen2.5-7B-Instruct"
    sft_path: Path = Path("datasets/sft/corpus.jsonl")
    dpo_path: Path = Path("datasets/preferences/corpus.jsonl")
    output_dir: Path = Path("models/lora/latest")
    sft_epochs: float = 1.0
    dpo_epochs: float = 1.0
    lora_r: int = 16
    lora_alpha: int = 32
    max_samples: int | None = None
    max_length: int = 512


def detect_backend() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _require_training_deps() -> None:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import peft  # noqa: F401
        import trl  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Training dependencies missing. Install with:\n"
            "  pip install torch transformers peft trl datasets accelerate bitsandbytes\n"
            f"Original error: {exc}"
        ) from exc


def run_lora_training(cfg: TrainConfig) -> dict[str, Any]:
    backend = detect_backend()
    sft_rows = _load_jsonl(cfg.sft_path)
    dpo_rows = _load_jsonl(cfg.dpo_path)
    if cfg.max_samples:
        sft_rows = sft_rows[: cfg.max_samples]
        dpo_rows = dpo_rows[: cfg.max_samples]

    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backend": backend,
        "platform": platform.platform(),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in asdict(cfg).items()},
        "sft_rows": len(sft_rows),
        "dpo_rows": len(dpo_rows),
    }

    if os.environ.get("AGENT_TRAIN_DRY_RUN") == "1":
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        (cfg.output_dir / "metadata.json").write_text(
            json.dumps({**metadata, "dry_run": True}, indent=2), encoding="utf-8"
        )
        return {**metadata, "status": "dry_run"}

    if not sft_rows and not dpo_rows:
        raise ValueError("no training rows; run corpus export first")

    _require_training_deps()
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    load_in_4bit = backend == "cuda"
    model_kwargs: dict[str, Any] = {}
    if load_in_4bit:
        model_kwargs["load_in_4bit"] = True
        model_kwargs["device_map"] = "auto"
    elif backend == "mps":
        model_kwargs["torch_dtype"] = torch.float16

    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model, trust_remote_code=True, **model_kwargs
    )
    lora_cfg = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)

    grad_accum = 1 if backend == "mps" else 4
    grad_checkpointing = backend != "mps"
    optim = "adamw_torch" if backend == "mps" else "adamw_torch_fused"
    adapter_dir = cfg.output_dir / "adapter"
    if sft_rows:
        sft_ds = Dataset.from_list([{"messages": r["messages"]} for r in sft_rows if r.get("messages")])
        sft_args = SFTConfig(
            output_dir=str(cfg.output_dir / "sft"),
            num_train_epochs=cfg.sft_epochs,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=grad_accum,
            gradient_checkpointing=grad_checkpointing,
            learning_rate=2e-4,
            logging_steps=1,
            logging_first_step=True,
            max_length=cfg.max_length,
            optim=optim,
            dataloader_pin_memory=False,
            save_strategy="epoch",
            report_to=[],
        )
        sft_trainer = SFTTrainer(
            model=model,
            args=sft_args,
            train_dataset=sft_ds,
            processing_class=tokenizer,
        )
        sft_trainer.train()

    if dpo_rows:
        dpo_ds = Dataset.from_list(
            [
                {
                    "prompt": r.get("prompt", ""),
                    "chosen": json.dumps(r.get("chosen", [])),
                    "rejected": json.dumps(r.get("rejected", [])),
                }
                for r in dpo_rows
                if r.get("prompt")
            ]
        )
        dpo_args = DPOConfig(
            output_dir=str(cfg.output_dir / "dpo"),
            num_train_epochs=cfg.dpo_epochs,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=grad_accum,
            gradient_checkpointing=grad_checkpointing,
            learning_rate=5e-5,
            logging_steps=1,
            logging_first_step=True,
            max_length=cfg.max_length,
            optim=optim,
            dataloader_pin_memory=False,
            save_strategy="epoch",
            report_to=[],
        )
        dpo_trainer = DPOTrainer(
            model=model,
            args=dpo_args,
            train_dataset=dpo_ds,
            processing_class=tokenizer,
        )
        dpo_trainer.train()

    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    metadata["status"] = "completed"
    (cfg.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LoRA fine-tune neighborhood agent")
    parser.add_argument("--base-model", default=os.environ.get("AGENT_TRAIN_BASE", "Qwen/Qwen2.5-7B-Instruct"))
    parser.add_argument("--sft", type=Path, default=Path("datasets/sft/corpus.jsonl"))
    parser.add_argument("--dpo", type=Path, default=Path("datasets/preferences/corpus.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("models/lora/latest"))
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--max-length", type=int, default=int(os.environ.get("AGENT_TRAIN_MAX_LENGTH", "512")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        os.environ["AGENT_TRAIN_DRY_RUN"] = "1"
    cfg = TrainConfig(
        base_model=args.base_model,
        sft_path=args.sft.resolve(),
        dpo_path=args.dpo.resolve(),
        output_dir=args.out.resolve(),
        max_samples=args.max_samples,
        max_length=args.max_length,
    )
    result = run_lora_training(cfg)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
