from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from companion.compound import route_compound
from companion.provider import OllamaCompiler
from companion.routing import RouteDecision, compiled_route, route
from companion.session import PlayerSession, resolve_revise

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "agent" / "eval" / "corpus"
EXTRA = ROOT / "evals" / "companion_extra.yaml"
EIGHTY_SEED = ROOT / "evals" / "eighty_seed.yaml"
CORE_TOOLS = {"set_time", "set_weather", "give_item", "summon_entity"}

# Honest Tier B (model) floors for warm Metal hosts — see evals/release-gates.yaml
TIER_B_MEDIAN_MAX_MS = 4500
TIER_B_CASE_MAX_MS = 8000
TIER_S_CASE_MAX_MS = 500


def _load_legacy_cases(limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    allocations = (
        ("world_settings.yaml", 34),
        ("give_items.yaml", 26),
        ("mobs.yaml", 26),
        ("adversarial.yaml", 8),
    )
    for filename, count in allocations:
        cases = yaml.safe_load((CORPUS / filename).read_text())["cases"]
        eligible = [case for case in cases if _expected_tools(case) <= CORE_TOOLS]
        for case in eligible[:count]:
            case = dict(case)
            case["_source"] = "legacy"
            selected.append(case)
    return selected[:limit]


def _load_yaml_cases(path: Path, source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case in yaml.safe_load(path.read_text())["cases"]:
        item = dict(case)
        item["_source"] = source
        out.append(item)
    return out


def _load_eighty_cases() -> list[dict[str, Any]]:
    return _load_yaml_cases(EIGHTY_SEED, "eighty_seed")


def _load_extra_cases() -> list[dict[str, Any]]:
    return _load_yaml_cases(EXTRA, "extra") + _load_eighty_cases()


def _load_cases(mode: str, limit: int) -> list[dict[str, Any]]:
    """Load offline cases.

    Modes:
      gate         — legacy fill + companion_extra + eighty_seed. Never truncates
                     product cases (extra/eighty); may exceed ``limit``.
      corpus       — all eighty_seed only (Wave 2 grounded seed).
      corpus-plus  — all eighty_seed + companion_extra.
    """
    if mode == "corpus":
        return _load_eighty_cases()
    if mode == "corpus-plus":
        return _load_extra_cases()

    # Gate: keep a legacy CORE_TOOLS sample of ``limit`` AND always include every
    # product row (companion_extra + eighty_seed). Never truncate the product corpus.
    legacy = _load_legacy_cases(limit)
    product = _load_extra_cases()
    print(
        f"NOTE: gate load = {len(legacy)} legacy + {len(product)} product "
        f"(no product truncation; total {len(legacy) + len(product)}).",
        flush=True,
    )
    return legacy + product


def _case_bucket(case: dict[str, Any]) -> str:
    family = case.get("paraphrase_family")
    if family:
        return str(family)
    case_id = str(case.get("id", "unknown"))
    parts = case_id.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return parts[0]


def _expected_tools(case: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in case.get("expect", {}).get("tool_any", [])
        if item.get("name") in CORE_TOOLS
    }


def _arguments_match(case: dict[str, Any], decision: RouteDecision) -> bool:
    expected_names = {
        item["name"] for item in case.get("expect", {}).get("tool_any", [])
    }
    if expected_names and not expected_names <= CORE_TOOLS:
        return decision.action is not None and decision.action.tool in expected_names
    if decision.action is None:
        return not _expected_tools(case)
    if decision.action.tool not in _expected_tools(case):
        return False
    probe = case.get("expect", {}).get("world_probe", {})
    args = decision.action.arguments
    if probe.get("kind") == "setting":
        setting = probe.get("setting")
        return args.get(setting) == probe.get("value")
    if probe.get("kind") == "inventory_has":
        return args.get("material") == probe.get("item")
    if probe.get("kind") == "mob_count":
        if args.get("entity") != probe.get("entity"):
            return False
        alternatives = []
        for tool in case.get("expect", {}).get("tool_any", []):
            if tool.get("name") == "summon_entity":
                alternatives.extend(tool.get("arguments_any", []))
        exact_counts = [item["count"] for item in alternatives if "count" in item]
        return not exact_counts or args.get("count") in exact_counts
    return True


def _extra_match(
    case: dict[str, Any],
    decision: RouteDecision,
    *,
    compound: list[RouteDecision] | None,
) -> bool:
    expect = case.get("expect", {})
    if "compound_tools" in expect:
        if not compound or len(compound) != len(expect["compound_tools"]):
            return False
        return all(
            item.action is not None and item.action.tool == tool
            for item, tool in zip(compound, expect["compound_tools"], strict=True)
        )
    if expect.get("cancel"):
        return decision.action is None and decision.route == "grammar.cancel"
    if expect.get("unresolved_or_clarify"):
        return decision.action is None and (
            decision.route == "unresolved" or "clarify" in decision.route
        )
    if expect.get("clarify"):
        if decision.action is not None:
            return False
        if "clarify" not in decision.route:
            return False
        if expect.get("pending_kind") and decision.pending_kind != expect["pending_kind"]:
            return False
        return bool(decision.message)
    if expect.get("refuse"):
        if decision.action is not None:
            return False
        needle = expect.get("route_contains", "refuse")
        return needle in decision.route
    tool = expect.get("tool")
    if tool:
        if decision.action is None or decision.action.tool != tool:
            return False
        expected_arguments = dict(expect.get("arguments", {}))
        for key in (
            "time",
            "weather",
            "material",
            "amount",
            "entity",
            "count",
            "template_id",
            "kind",
            "length",
            "width",
            "depth",
            "height",
        ):
            if key in expect:
                expected_arguments[key] = expect[key]
        for key, value in expected_arguments.items():
            if decision.action.arguments.get(key) != value:
                return False
        return True
    return False


def _decide_product_case(
    case: dict[str, Any],
    index: int,
) -> tuple[RouteDecision, list[RouteDecision] | None]:
    """Route a product case, including session revise when ``prior`` is set."""
    job_id = f"eval-{index}"
    prior = case.get("prior")
    if prior:
        session = PlayerSession()
        session.remember_action(
            tool=str(prior["tool"]),
            arguments=dict(prior.get("arguments") or {}),
            message="prior build",
        )
        decision = resolve_revise(
            prompt=case["prompt"], session=session, job_id=job_id
        )
        if decision is None:
            decision = RouteDecision(
                route="unresolved",
                tier="B",
                message="revise did not apply",
            )
        return decision, None
    compound = route_compound(case["prompt"], job_id)
    if compound and "compound_tools" in case.get("expect", {}):
        return compound[0], compound
    perception = case.get("perception") or {}
    return route(
        case["prompt"],
        job_id,
        has_finishable_wall=bool(perception.get("finishable_opening")),
    ), None


def _bucket_summary(
    cases: list[dict[str, Any]], results: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    holdout_pass = 0
    holdout_total = 0
    for case, result in zip(cases, results, strict=True):
        bucket = _case_bucket(case)
        buckets[bucket].append(bool(result["passed"]))
        if case.get("holdout"):
            holdout_total += 1
            if result["passed"]:
                holdout_pass += 1
    by_bucket = {
        name: {
            "cases": len(flags),
            "passed": sum(flags),
            "accuracy": (sum(flags) / len(flags)) if flags else 0.0,
        }
        for name, flags in sorted(buckets.items())
    }
    by_bucket["__holdout__"] = {
        "cases": holdout_total,
        "passed": holdout_pass,
        "accuracy": (holdout_pass / holdout_total) if holdout_total else 1.0,
    }
    return by_bucket


async def run(mode: str, limit: int, *, skip_model: bool = False) -> dict[str, Any]:
    cases = _load_cases(mode, limit)
    compiler: OllamaCompiler | None = None
    if not skip_model:
        compiler = OllamaCompiler()
        await compiler.warm_compiler()
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        started = time.perf_counter()
        used_model = False
        error = ""
        if case.get("_source") != "legacy":
            decision, compound = _decide_product_case(case, index)
            if compound is not None:
                passed = _extra_match(case, decision, compound=compound)
            else:
                passed = _extra_match(case, decision, compound=None)
                if (
                    not passed
                    and not case.get("prior")
                    and decision.route == "unresolved"
                    and case.get("expect", {}).get("tool")
                    and compiler is not None
                ):
                    # Allow model compile for ambiguous template phrasing only.
                    used_model = True
                    try:
                        intent = await compiler.compile(
                            prompt=case["prompt"],
                            context={
                                "world": "minecraft:overworld",
                                "gamemode": "creative",
                            },
                        )
                        decision = compiled_route(intent, f"eval-{index}")
                        passed = _extra_match(case, decision, compound=None)
                    except Exception as exception:
                        error = str(exception)
                        passed = False
        else:
            compound = route_compound(case["prompt"], f"eval-{index}")
            decision = route(case["prompt"], f"eval-{index}")
            used_model = decision.route == "unresolved"
            if used_model and compiler is not None:
                try:
                    intent = await compiler.compile(
                        prompt=case["prompt"],
                        context={"world": "minecraft:overworld", "gamemode": "creative"},
                    )
                    decision = compiled_route(intent, f"eval-{index}")
                except Exception as exception:
                    error = str(exception)
            elif used_model and compiler is None:
                error = "model skipped"
            passed = not error and _arguments_match(case, decision)

        latency_ms = int((time.perf_counter() - started) * 1000)
        results.append(
            {
                "id": case["id"],
                "prompt": case["prompt"],
                "passed": passed,
                "route": decision.route,
                "tool": decision.action.tool if decision.action else None,
                "arguments": decision.action.arguments if decision.action else {},
                "used_model": used_model,
                "latency_ms": latency_ms,
                "error": error,
                "source": case.get("_source", "legacy"),
                "bucket": _case_bucket(case),
                "holdout": bool(case.get("holdout")),
            }
        )
        print(
            f"[{index + 1:03d}/{len(cases):03d}] "
            f"{'PASS' if passed else 'FAIL'} {latency_ms:5d}ms "
            f"{case['id']} -> {decision.route}",
            flush=True,
        )
    passed_count = sum(item["passed"] for item in results)
    model_latencies = [item["latency_ms"] for item in results if item["used_model"]]
    deterministic = [item for item in results if not item["used_model"]]
    model_results = [item for item in results if item["used_model"]]
    safety_results = [
        item
        for item, case in zip(results, cases, strict=True)
        if (case.get("_source") == "legacy" and not _expected_tools(case))
        or case.get("expect", {}).get("refuse")
    ]
    by_bucket = _bucket_summary(cases, results)
    summary = {
        "mode": mode,
        "cases": len(results),
        "passed": passed_count,
        "accuracy": passed_count / len(results) if results else 0,
        "model_cases": len(model_latencies),
        "model_accuracy": (
            sum(item["passed"] for item in model_results) / len(model_results)
            if model_results
            else 1.0
        ),
        "deterministic_accuracy": (
            sum(item["passed"] for item in deterministic) / len(deterministic)
            if deterministic
            else 1.0
        ),
        "deterministic_latency_max_ms": max(
            (item["latency_ms"] for item in deterministic), default=0
        ),
        "safety_accuracy": (
            sum(item["passed"] for item in safety_results) / len(safety_results)
            if safety_results
            else 1.0
        ),
        "model_latency_median_ms": (
            int(statistics.median(model_latencies)) if model_latencies else 0
        ),
        "model_latency_max_ms": max(model_latencies, default=0),
        "by_bucket": by_bucket,
        "results": results,
    }
    return summary


def _print_buckets(summary: dict[str, Any]) -> None:
    print("\nBY BUCKET:", flush=True)
    for name, stats in summary.get("by_bucket", {}).items():
        print(
            f"  {name:28} {stats['passed']:3d}/{stats['cases']:3d} "
            f"({stats['accuracy']:.1%})",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--mode",
        choices=("gate", "corpus", "corpus-plus"),
        default="gate",
        help="gate=locked SLO mix; corpus=all eighty_seed; corpus-plus=+companion_extra",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip Ollama warm/compile (corpus modes default to this).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    skip_model = args.skip_model or args.mode in {"corpus", "corpus-plus"}
    if args.output is None:
        suffix = "offline-latest.json" if args.mode == "gate" else f"offline-{args.mode}.json"
        args.output = ROOT / "data" / "companion-evals" / suffix
    summary = asyncio.run(run(args.mode, args.limit, skip_model=skip_model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"RESULT: {summary['passed']}/{summary['cases']} "
        f"({summary['accuracy']:.1%}), "
        f"model median={summary['model_latency_median_ms']}ms "
        f"max={summary['model_latency_max_ms']}ms "
        f"mode={summary['mode']}",
        flush=True,
    )
    _print_buckets(summary)

    if args.mode == "gate":
        gates_pass = (
            summary["cases"] >= 100
            and summary["accuracy"] >= 0.95
            and summary["deterministic_accuracy"] >= 0.98
            and summary["model_accuracy"] >= 0.90
            and summary["safety_accuracy"] == 1.0
            and summary["deterministic_latency_max_ms"] <= TIER_S_CASE_MAX_MS
            and summary["model_latency_median_ms"] <= TIER_B_MEDIAN_MAX_MS
            and summary["model_latency_max_ms"] <= TIER_B_CASE_MAX_MS
        )
        print(f"GATES: {'PASS' if gates_pass else 'FAIL'}", flush=True)
        return 0 if gates_pass else 1

    # Corpus modes: require near-perfect routing on the grounded seed.
    corpus_pass = (
        summary["cases"] >= 80
        and summary["accuracy"] >= 0.95
        and summary["deterministic_accuracy"] >= 0.98
        and summary["safety_accuracy"] == 1.0
    )
    print(f"CORPUS: {'PASS' if corpus_pass else 'FAIL'}", flush=True)
    return 0 if corpus_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
