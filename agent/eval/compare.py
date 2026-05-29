"""Multi-model / multi-strategy eval comparison."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent.eval.runner import run
from agent.eval.strategy import apply_strategy_env, resolve_strategy, strategy_env


@dataclass
class VariantResult:
    label: str
    model: str | None
    strategy_id: str
    summary: dict[str, Any]
    baseline_diff: dict[str, Any] | None
    report_path: str


def compare_variants(
    *,
    repo_root: Path,
    orchestrator_url: str,
    api_token: str,
    variants: list[dict[str, Any]],
    mode: str = "spec",
    output_dir: Path | None = None,
    compare_baseline: Path | None = None,
) -> dict[str, Any]:
    """Run the same eval suite under multiple model/strategy variants.

    Each variant dict supports:
      - label: str (required)
      - model: str | None
      - strategy: str | None (prompt strategy id)
    """

    output_dir = output_dir or (repo_root / "data" / "eval-runs" / "compare")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[VariantResult] = []
    for v in variants:
        label = str(v["label"])
        model = v.get("model")
        strategy = resolve_strategy(v.get("strategy"))
        report_path = output_dir / f"{label}.json"

        with strategy_env(strategy):
            payload = run(
                repo_root=repo_root,
                orchestrator_url=orchestrator_url,
                api_token=api_token,
                mode=mode,  # type: ignore[arg-type]
                model_override=model,
                write_report_dir=report_path,
                compare_baseline=compare_baseline,
                exit_on_fail=False,
            )
        payload["strategy"] = {
            "id": strategy.id,
            "env": apply_strategy_env(strategy),
        }
        (output_dir / f"{label}.full.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

        results.append(
            VariantResult(
                label=label,
                model=model,
                strategy_id=strategy.id,
                summary=payload["summary"],
                baseline_diff=payload.get("baseline_diff"),
                report_path=str(report_path / "report.json"),
            )
        )

    ranked = sorted(
        results,
        key=lambda r: (
            -float(r.summary.get("strict_pass_rate") or 0),
            r.summary.get("safety_fail_count") or 0,
            r.summary.get("failed") or 0,
        ),
    )

    return {
        "variants": [asdict(r) for r in results],
        "ranking": [r.label for r in ranked],
        "winner": ranked[0].label if ranked else None,
    }
