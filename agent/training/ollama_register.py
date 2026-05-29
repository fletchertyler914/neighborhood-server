"""Register a fine-tuned LoRA adapter as an Ollama model."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def write_modelfile(
    *,
    gguf_path: Path,
    model_name: str,
    out_path: Path,
    system_prompt_path: Path | None = None,
) -> Path:
    system = ""
    sp = system_prompt_path or (_repo_root() / "agent" / "prompts" / "system.md")
    if sp.exists():
        system = sp.read_text(encoding="utf-8").strip()
    content = f'FROM {gguf_path}\n\nPARAMETER temperature 0.2\n\nSYSTEM """{system}"""\n'
    out_path.write_text(content, encoding="utf-8")
    return out_path


def register_ollama_model(
    *,
    adapter_dir: Path,
    model_name: str = "neighborhood-qwen2.5-7b:v1",
    gguf_path: Path | None = None,
    auto_merge: bool = False,
) -> dict[str, str]:
    """Create Ollama model from GGUF or emit instructions if conversion tools missing."""

    adapter_dir = adapter_dir.resolve()
    meta_path = adapter_dir / "metadata.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    models_dir = _repo_root() / "models" / "ollama"
    models_dir.mkdir(parents=True, exist_ok=True)

    if gguf_path is None:
        gguf_path = models_dir / f"{model_name.replace(':', '_')}.gguf"

    if not gguf_path.exists():
        if auto_merge:
            script = _repo_root() / "scripts" / "merge-lora-to-gguf.sh"
            if script.exists():
                try:
                    subprocess.run(
                        [str(script), str(adapter_dir), str(gguf_path)],
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    return {
                        "status": "merge_failed",
                        "message": str(exc),
                        "adapter_dir": str(adapter_dir),
                        "gguf_path": str(gguf_path),
                    }
            if gguf_path.exists():
                # Continue below and create the Ollama model.
                pass
            else:
                return {
                    "status": "needs_gguf",
                    "message": (
                        "GGUF not found after auto-merge. Set LLAMA_CPP_DIR or pass --gguf."
                    ),
                    "adapter_dir": str(adapter_dir),
                    "gguf_path": str(gguf_path),
                }
        if gguf_path.exists():
            pass
        else:
            return {
                "status": "needs_gguf",
                "message": (
                    "GGUF not found. Merge LoRA adapter to GGUF with llama.cpp, e.g.:\n"
                    "  python convert.py models/lora/latest/adapter --outfile models/ollama/neighborhood.gguf\n"
                    "  ./quantize models/ollama/neighborhood.gguf models/ollama/neighborhood-q4.gguf Q4_K_M\n"
                    f"Then re-run with --gguf {gguf_path}"
                ),
                "adapter_dir": str(adapter_dir),
            }

    modelfile = write_modelfile(
        gguf_path=gguf_path,
        model_name=model_name,
        out_path=models_dir / "Modelfile",
    )
    if shutil.which("ollama") is None:
        return {
            "status": "needs_ollama",
            "message": "ollama CLI not found; install from https://ollama.com",
            "modelfile": str(modelfile),
        }

    subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile)],
        check=True,
    )
    return {"status": "created", "model": model_name, "modelfile": str(modelfile)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Register fine-tuned model with Ollama")
    parser.add_argument("--adapter", type=Path, default=Path("models/lora/latest/adapter"))
    parser.add_argument("--model-name", default="neighborhood-qwen2.5-7b:v1")
    parser.add_argument("--gguf", type=Path, default=None)
    parser.add_argument("--auto-merge", action="store_true")
    args = parser.parse_args()
    result = register_ollama_model(
        adapter_dir=args.adapter,
        model_name=args.model_name,
        gguf_path=args.gguf.resolve() if args.gguf else None,
        auto_merge=args.auto_merge,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
