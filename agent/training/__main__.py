"""CLI for agent training data extraction and corpus fine-tuning."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent.training.feedback import (
    build_dpo_pairs,
    build_sft,
    join_feedback,
    write_jsonl,
)
from agent.training.pairs import build_pairs_from_reviews, write_pairs_jsonl


def _cmd_pairs(args: argparse.Namespace) -> None:
    pairs = build_pairs_from_reviews(args.reviews.resolve())
    n = write_pairs_jsonl(pairs, args.out.resolve())
    print(f"pairs={n} path={args.out}")
    if n == 0:
        raise SystemExit(1)


def _cmd_feedback(args: argparse.Namespace) -> None:
    rows = list(join_feedback(args.feedback, args.audit))
    good = sum(1 for r in rows if r.rating == "good")
    bad = sum(1 for r in rows if r.rating == "bad")
    if args.report:
        print(json.dumps({"rows": len(rows), "good": good, "bad": bad}, indent=2))
        return
    system_prompt = (
        args.system_prompt.read_text(encoding="utf-8")
        if args.system_prompt.exists()
        else None
    )
    sft = build_sft(
        rows,
        system_prompt=system_prompt,
        include_bad_as_negative=args.include_bad_as_negative,
    )
    dpo = build_dpo_pairs(rows)
    sft_n = write_jsonl(sft, args.sft_out)
    dpo_n = write_jsonl(dpo, args.dpo_out)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "good": good,
                "bad": bad,
                "sft_examples": sft_n,
                "dpo_pairs": dpo_n,
                "sft_out": str(args.sft_out),
                "dpo_out": str(args.dpo_out),
            },
            indent=2,
        )
    )


def _cmd_build_datasets(args: argparse.Namespace) -> None:
    from agent.training.build_datasets import export_corpus_datasets

    run_dir = args.run.resolve()
    if run_dir.name == "latest" and run_dir.is_symlink():
        run_dir = run_dir.resolve()
    stats = export_corpus_datasets(
        run_dir=run_dir,
        sft_out=args.sft_out.resolve(),
        dpo_out=args.dpo_out.resolve(),
        system_prompt_path=args.system_prompt.resolve(),
    )
    print(json.dumps(stats, indent=2))


def _cmd_sample_diverse(args: argparse.Namespace) -> None:
    from agent.training.sample_diverse import sample_diverse

    temps = [float(x.strip()) for x in args.temperatures.split(",") if x.strip()]
    result = sample_diverse(run_dir=args.run.resolve(), temperatures=temps)
    print(json.dumps(result, indent=2))


def _cmd_lora(args: argparse.Namespace) -> None:
    from agent.training.lora_finetune import TrainConfig, run_lora_training

    if args.dry_run:
        os.environ["AGENT_TRAIN_DRY_RUN"] = "1"
    cfg = TrainConfig(
        base_model=args.base_model,
        sft_path=args.sft.resolve(),
        dpo_path=args.dpo.resolve(),
        output_dir=args.out.resolve(),
        max_samples=args.max_samples,
    )
    print(json.dumps(run_lora_training(cfg), indent=2))


def _cmd_ollama_register(args: argparse.Namespace) -> None:
    from agent.training.ollama_register import register_ollama_model

    result = register_ollama_model(
        adapter_dir=args.adapter,
        model_name=args.model_name,
        gguf_path=args.gguf.resolve() if args.gguf else None,
        auto_merge=args.auto_merge,
    )
    print(json.dumps(result, indent=2))


def _cmd_compare_models(args: argparse.Namespace) -> None:
    from agent.training.compare_models import compare_models_on_corpus

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    payload = compare_models_on_corpus(
        models=models, limit=args.limit, category=args.category
    )
    print(json.dumps(payload, indent=2))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m agent.training")
    sub = parser.add_subparsers(dest="command", required=True)

    pairs_p = sub.add_parser("pairs", help="Build preference pairs from labeled reviews")
    pairs_p.add_argument("reviews", type=Path)
    pairs_p.add_argument("out", type=Path)
    pairs_p.set_defaults(func=_cmd_pairs)

    fb_p = sub.add_parser("feedback", help="SFT + DPO from /agent good|bad ratings")
    fb_p.add_argument("--feedback", type=Path, default=None)
    fb_p.add_argument("--audit", type=Path, default=None)
    fb_p.add_argument("--sft-out", type=Path, default=Path("training/sft-from-feedback.jsonl"))
    fb_p.add_argument("--dpo-out", type=Path, default=Path("training/dpo-from-feedback.jsonl"))
    fb_p.add_argument("--system-prompt", type=Path, default=Path("agent/prompts/system.md"))
    fb_p.add_argument("--include-bad-as-negative", action="store_true")
    fb_p.add_argument("--report", action="store_true")
    fb_p.set_defaults(func=_cmd_feedback)

    bd_p = sub.add_parser("build-datasets", help="Export corpus run to SFT/DPO JSONL")
    bd_p.add_argument("--run", type=Path, default=Path("data/corpus-runs/latest"))
    bd_p.add_argument("--sft-out", type=Path, default=Path("datasets/sft/corpus.jsonl"))
    bd_p.add_argument("--dpo-out", type=Path, default=Path("datasets/preferences/corpus.jsonl"))
    bd_p.add_argument("--system-prompt", type=Path, default=Path("agent/prompts/system.md"))
    bd_p.set_defaults(func=_cmd_build_datasets)

    sd_p = sub.add_parser("sample-diverse", help="Resample failing corpus at varied temperatures")
    sd_p.add_argument("--run", type=Path, default=Path("data/corpus-runs/latest"))
    sd_p.add_argument("--temperatures", default="0.0,0.3,0.7")
    sd_p.set_defaults(func=_cmd_sample_diverse)

    lf_p = sub.add_parser("lora-finetune", help="LoRA fine-tune from SFT/DPO JSONL")
    lf_p.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    lf_p.add_argument("--sft", type=Path, default=Path("datasets/sft/corpus.jsonl"))
    lf_p.add_argument("--dpo", type=Path, default=Path("datasets/preferences/corpus.jsonl"))
    lf_p.add_argument("--out", type=Path, default=Path("models/lora/latest"))
    lf_p.add_argument("--max-samples", type=int, default=None)
    lf_p.add_argument("--dry-run", action="store_true")
    lf_p.set_defaults(func=_cmd_lora)

    or_p = sub.add_parser("ollama-register", help="Register fine-tuned model with Ollama")
    or_p.add_argument("--adapter", type=Path, default=Path("models/lora/latest/adapter"))
    or_p.add_argument("--model-name", default="neighborhood-qwen2.5-7b:v1")
    or_p.add_argument("--gguf", type=Path, default=None)
    or_p.add_argument("--auto-merge", action="store_true")
    or_p.set_defaults(func=_cmd_ollama_register)

    cm_p = sub.add_parser("compare-models", help="Compare models on corpus subset")
    cm_p.add_argument("--models", default="qwen2.5:7b-instruct,neighborhood-qwen2.5-7b:v1")
    cm_p.add_argument("--limit", type=int, default=30)
    cm_p.add_argument("--category")
    cm_p.set_defaults(func=_cmd_compare_models)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
