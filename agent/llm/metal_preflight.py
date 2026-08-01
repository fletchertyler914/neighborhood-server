"""Validate host Ollama Metal / MLX residency before bake-off or agent use."""

from __future__ import annotations

import time
from typing import Any

import httpx

MIN_OLLAMA = (0, 31, 0)
MIN_VRAM_RATIO = 0.85
NUM_CTX = 8192


def _parse_version(text: str) -> tuple[int, ...]:
    for part in text.replace(",", " ").split():
        if part and part[0].isdigit() and "." in part:
            bits: list[int] = []
            for b in part.strip().split("."):
                try:
                    bits.append(int(b))
                except ValueError:
                    break
            if bits:
                return tuple(bits)
    return (0,)


def _get_json(client: httpx.Client, base: str, path: str) -> Any:
    r = client.get(f"{base.rstrip('/')}{path}")
    r.raise_for_status()
    return r.json()


def unload_all(client: httpx.Client, base: str) -> None:
    data = _get_json(client, base, "/api/ps")
    for m in data.get("models") or []:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        client.post(
            f"{base.rstrip('/')}/api/generate",
            json={"model": name, "keep_alive": 0, "prompt": ""},
            timeout=60.0,
        )
    for _ in range(40):
        data = _get_json(client, base, "/api/ps")
        if not (data.get("models") or []):
            return
        time.sleep(0.5)


def load_and_probe(client: httpx.Client, base: str, model: str) -> dict[str, Any]:
    client.post(
        f"{base.rstrip('/')}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "options": {"num_ctx": NUM_CTX, "num_predict": 8},
            "keep_alive": "10m",
            "think": False,
        },
        timeout=180.0,
    )
    time.sleep(0.5)
    data = _get_json(client, base, "/api/ps")
    for m in data.get("models") or []:
        name = (m.get("name") or m.get("model") or "").lower()
        if model.lower() in name or name in model.lower():
            return m
    models = data.get("models") or []
    if len(models) == 1:
        return models[0]
    raise RuntimeError(f"model {model} not resident after warmup; ps={data}")


def show_model(client: httpx.Client, base: str, model: str) -> dict[str, Any]:
    r = client.post(
        f"{base.rstrip('/')}/api/show",
        json={"name": model},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def validate_model(base: str, model: str, *, unload_first: bool = True) -> dict[str, Any]:
    base = base.replace("host.docker.internal", "127.0.0.1").rstrip("/")
    report: dict[str, Any] = {"model": model, "ok": False, "checks": []}

    with httpx.Client(timeout=30.0) as client:
        try:
            ver_resp = client.get(f"{base}/api/version")
            ver_resp.raise_for_status()
            try:
                ver_obj = ver_resp.json()
                ver_txt = str(ver_obj.get("version") or ver_resp.text)
            except Exception:
                ver_txt = ver_resp.text
            ver = _parse_version(ver_txt)
        except Exception:
            client.get(f"{base}/api/tags").raise_for_status()
            ver = MIN_OLLAMA
            ver_txt = "unknown"
        report["ollama_version"] = ver_txt.strip()
        if ver < MIN_OLLAMA:
            report["checks"].append(
                {
                    "name": "ollama_version",
                    "ok": False,
                    "detail": f"need >={'.'.join(map(str, MIN_OLLAMA))}, got {ver}",
                }
            )
            return report
        report["checks"].append(
            {"name": "ollama_version", "ok": True, "detail": str(ver)}
        )

        lower = model.lower()
        if "gemma" in lower and "-mlx" not in lower and ":mlx" not in lower:
            report["checks"].append(
                {
                    "name": "gemma_mlx_tag",
                    "ok": False,
                    "detail": (
                        f"{model} is not an MLX tag. Use gemma4:12b-mlx "
                        "(plain gemma4:12b is GGUF without MTP)."
                    ),
                }
            )
            return report
        if "gemma" in lower:
            report["checks"].append(
                {"name": "gemma_mlx_tag", "ok": True, "detail": "mlx tag present"}
            )

        show = show_model(client, base, model)
        details = show.get("details") or {}
        fmt = (details.get("format") or "").lower()
        report["details"] = {
            "family": details.get("family"),
            "parameter_size": details.get("parameter_size"),
            "quantization_level": details.get("quantization_level"),
            "format": fmt,
        }
        report["checks"].append(
            {
                "name": "model_format",
                "ok": True,
                "detail": (
                    f"format={fmt or 'n/a'} family={details.get('family')} "
                    f"quant={details.get('quantization_level')}"
                ),
            }
        )

        if unload_first:
            unload_all(client, base)
            report["checks"].append(
                {"name": "exclusive_unload", "ok": True, "detail": "no resident models"}
            )

        ps = load_and_probe(client, base, model)
        size = float(ps.get("size") or 0) or 1.0
        vram = float(ps.get("size_vram") or 0)
        ratio = vram / size
        ctx = int(ps.get("context_length") or 0)
        ps_fmt = ((ps.get("details") or {}).get("format") or fmt or "").lower()
        report["residency"] = {
            "size": size,
            "size_vram": vram,
            "vram_ratio": round(ratio, 3),
            "context_length": ctx,
            "format": ps_fmt,
        }

        gpu_ok = ratio >= MIN_VRAM_RATIO
        report["checks"].append(
            {
                "name": "gpu_residency",
                "ok": gpu_ok,
                "detail": (
                    f"vram_ratio={ratio:.2%} (need ≥{MIN_VRAM_RATIO:.0%}); "
                    f"format={ps_fmt or 'n/a'}; context_length={ctx}"
                ),
            }
        )

        if "gemma" in lower and ps_fmt == "gguf":
            # -mlx tag should not load as plain gguf — hard fail
            report["checks"].append(
                {
                    "name": "gemma_not_gguf",
                    "ok": False,
                    "detail": "gemma MLX tag loaded as gguf — wrong weights",
                }
            )

        if ctx > 32768:
            report["checks"].append(
                {
                    "name": "context_cap_note",
                    "ok": True,
                    "detail": f"resident ctx={ctx}; requests force num_ctx={NUM_CTX}",
                }
            )

        report["ok"] = all(c["ok"] for c in report["checks"])
        return report
