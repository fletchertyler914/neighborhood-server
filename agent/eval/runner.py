from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx

from agent.eval.assertions import AssertionFailure, assert_spec, normalize_tool_calls
from agent.eval.case import CaseMode, EvalCase
from agent.eval.coverage import validate_coverage
from agent.eval.loader import filter_cases, load_cases
from agent.eval.envelope import build_job_envelope
from agent.eval.quarantine import filter_quarantined
from agent.eval.strategy import resolve_strategy
from agent.eval.world import Box, assert_world, clear_box
from agent.tool_registry import TOOLS_SCHEMA_VERSION, TOOLS_VERSION


@dataclass(frozen=True)
class RunManifest:
    git_sha: str | None
    timestamp_iso: str
    eval_mode: bool
    model: str | None
    tools_version: str
    tools_schema_version: int
    flags: dict[str, str]


@dataclass
class CaseResult:
    case_id: str
    mode: str
    severity: str
    ok: bool
    status: str
    steps: int
    model: str
    job_id: str | None = None
    prompt: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    trace_hash: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def _utc_now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _git_sha(repo_root: Path) -> str | None:
    head = repo_root / ".git" / "HEAD"
    if not head.exists():
        return None
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            ref_path = repo_root / ".git" / ref.removeprefix("ref: ").strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()[:12]
        return ref[:12]
    except Exception:
        return None


def run(
    *,
    repo_root: Path,
    orchestrator_url: str,
    api_token: str,
    cases_dir: Path | None = None,
    mode: Literal["spec", "world", "both"] = "spec",
    case_id: str | None = None,
    category: str | None = None,
    player: str = ".EvalBot",
    uuid: str = "00000000-0000-0000-0000-000000000000",
    x: float = 0,
    y: float = 80,
    z: float = 0,
    write_report_dir: Path | None = None,
    compare_baseline: Path | None = None,
    save_baseline: Path | None = None,
    exit_on_fail: bool = True,
    model_override: str | None = None,
) -> dict[str, Any]:
    cases_dir = cases_dir or (repo_root / "agent" / "eval" / "cases")
    suite = load_cases(cases_dir)
    coverage_path = repo_root / "agent" / "eval" / "coverage.yaml"
    if os.environ.get("AGENT_EVAL_ENFORCE_COVERAGE", "1") == "1":
        cov_errors = validate_coverage(suite.cases, coverage_path)
        if cov_errors:
            raise SystemExit("coverage validation failed:\n" + "\n".join(cov_errors))

    quarantine_path = repo_root / "agent" / "eval" / "quarantine.yaml"
    cases = filter_quarantined(suite.cases, quarantine_path)
    selected = filter_cases(cases, case_id=case_id, category=category)
    if mode != "both":
        selected = filter_cases(selected, mode=mode)

    effective_model = (
        model_override
        or os.environ.get("AGENT_EVAL_MODEL")
        or os.environ.get("OLLAMA_MODEL")
    )
    strategy = resolve_strategy()
    manifest = RunManifest(
        git_sha=_git_sha(repo_root),
        timestamp_iso=_utc_now_iso(),
        eval_mode=True,
        model=effective_model,
        tools_version=TOOLS_VERSION,
        tools_schema_version=TOOLS_SCHEMA_VERSION,
        flags={
            **{k: v for k, v in os.environ.items() if k.startswith("AGENT_EVAL_")},
            "AGENT_PROMPT_STRATEGY": strategy.id,
        },
    )
    cases_by_id = {c.id: c for c in selected}

    headers = {"Authorization": f"Bearer {api_token}"}
    results: list[CaseResult] = []
    # World cases that drive bigger reasoning models (qwen3:8b with think:false
    # on cold tool-schema load) can take >60s per job. Cap at the orchestrator
    # job timeout plus a small buffer.
    client_timeout = float(os.environ.get("AGENT_EVAL_CLIENT_TIMEOUT_SEC", "180"))
    with httpx.Client(timeout=client_timeout) as client:
        for c in selected:
            if CaseMode.spec in c.modes and mode in ("spec", "both"):
                results.append(
                    _run_spec_case_with_retries(
                        client,
                        orchestrator_url,
                        headers,
                        c,
                        player=player,
                        uuid=uuid,
                        x=x,
                        y=y,
                        z=z,
                        model_override=model_override,
                    )
                )
            if CaseMode.world in c.modes and mode in ("world", "both"):
                results.append(
                    _run_world_case(
                        client,
                        orchestrator_url,
                        headers,
                        c,
                        player=player,
                        uuid=uuid,
                        x=x,
                        y=y,
                        z=z,
                        model_override=model_override,
                    )
                )

    baseline_diff = (
        compare_to_baseline(results, compare_baseline, cases_by_id=cases_by_id)
        if compare_baseline
        else None
    )
    envelopes = [
        build_job_envelope(
            case_id=r.case_id,
            mode=r.mode,
            job_id=r.job_id,
            status=r.status,
            steps=r.steps,
            model=r.model,
            trace=r.trace,
            failures=r.failures,
            prompt=r.prompt or (cases_by_id[r.case_id].prompt if r.case_id in cases_by_id else None),
            strategy_id=strategy.id,
        )
        for r in results
    ]
    payload = {
        "manifest": asdict(manifest),
        "strategy_id": strategy.id,
        "results": [asdict(r) for r in results],
        "envelopes": envelopes,
        "summary": summarize(results),
        "baseline_diff": baseline_diff,
    }
    if save_baseline:
        write_baseline(save_baseline, payload)
    if write_report_dir:
        write_report_dir.mkdir(parents=True, exist_ok=True)
        (write_report_dir / "report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        with (write_report_dir / "envelopes.jsonl").open("w", encoding="utf-8") as ef:
            for env in envelopes:
                ef.write(json.dumps(env, sort_keys=True) + "\n")
    has_baseline_regressions = bool(baseline_diff and baseline_diff["regressions"])
    if exit_on_fail:
        if has_baseline_regressions:
            raise SystemExit(2)
        # When a baseline is provided, the baseline is the source of truth — only
        # fail on regressions or new failures that aren't in the baseline.
        if baseline_diff is None and payload["summary"]["failed"]:
            raise SystemExit(2)
    return payload


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "strict_pass_rate": (passed / total) if total else 1.0,
        "safety_fail_count": sum(
            1 for r in results if not r.ok and r.severity == "P0-safety"
        ),
        "failures": [r.case_id for r in results if not r.ok],
    }


def _run_spec_case_with_retries(
    client: httpx.Client,
    orchestrator_url: str,
    headers: dict[str, str],
    case: EvalCase,
    *,
    player: str,
    uuid: str,
    x: float,
    y: float,
    z: float,
    model_override: str | None = None,
) -> CaseResult:
    max_attempts = 1
    if case.determinism == "relaxed" and case.retries_allowed > 0:
        max_attempts = 1 + int(case.retries_allowed)

    last: CaseResult | None = None
    for attempt in range(max_attempts):
        last = _run_spec_case(
            client,
            orchestrator_url,
            headers,
            case,
            player=player,
            uuid=uuid,
            x=x,
            y=y,
            z=z,
            model_override=model_override,
        )
        if last.ok:
            return last
    assert last is not None
    return last


def _run_spec_case(
    client: httpx.Client,
    orchestrator_url: str,
    headers: dict[str, str],
    case: EvalCase,
    *,
    player: str,
    uuid: str,
    x: float,
    y: float,
    z: float,
    model_override: str | None = None,
) -> CaseResult:
    req: dict[str, Any] = {
        "player": player,
        "uuid": uuid,
        "x": x,
        "y": y,
        "z": z,
        "prompt": case.prompt,
        "dry_run": True,
        "eval_mode": True,
    }
    if model_override:
        req["eval_model"] = model_override
    resp = client.post(f"{orchestrator_url.rstrip('/')}/v1/jobs", headers=headers, json=req)
    resp.raise_for_status()
    job = resp.json()

    job_id = job.get("job_id")
    status = job.get("status")
    steps = int(job.get("steps") or 0)
    model = job.get("model") or ""
    tool_calls = job.get("tool_calls") or []
    norm_trace = normalize_tool_calls(tool_calls)

    failures: list[AssertionFailure] = []
    if case.expect_spec:
        failures = assert_spec(
            expect=case.expect_spec,
            actual_status=status,
            actual_steps=steps,
            tool_calls=tool_calls,
        )

    ok = not failures
    return CaseResult(
        case_id=case.id,
        mode="spec",
        severity=case.severity.value,
        ok=ok,
        status=status,
        steps=steps,
        model=model,
        job_id=job_id,
        prompt=case.prompt,
        failures=[asdict(f) for f in failures],
        trace_hash=_trace_hash(norm_trace),
        trace=norm_trace,
    )


def _run_world_case(
    client: httpx.Client,
    orchestrator_url: str,
    headers: dict[str, str],
    case: EvalCase,
    *,
    player: str,
    uuid: str,
    x: float,
    y: float,
    z: float,
    model_override: str | None = None,
) -> CaseResult:
    if case.expect_world and case.expect_world.sandbox_box:
        box = case.expect_world.sandbox_box
        if len(box) == 6:
            clear_box(Box(box[0], box[1], box[2], box[3], box[4], box[5]))

    _maybe_teleport_to_sandbox(case, player)

    if os.environ.get("AGENT_EVAL_ALLOW_WORLD_MUTATION") != "1":
        return CaseResult(
            case_id=case.id,
            mode="world",
            severity=case.severity.value,
            ok=False,
            status="infra",
            steps=0,
            model="",
            prompt=case.prompt,
            failures=[
                {
                    "kind": "world_guard",
                    "message": "world eval requires AGENT_EVAL_ALLOW_WORLD_MUTATION=1",
                    "details": None,
                }
            ],
            trace=[],
        )

    # World cases must reflect the live player. Otherwise the agent receives
    # synthetic coords and builds nowhere near the player, making world probes
    # pass trivially.
    live_x, live_y, live_z = _live_player_pos(player) or (x, y, z)
    req: dict[str, Any] = {
        "player": player,
        "uuid": uuid,
        "x": live_x,
        "y": live_y,
        "z": live_z,
        "prompt": case.prompt,
        "dry_run": False,
        "eval_mode": True,
    }
    if model_override:
        req["eval_model"] = model_override
    resp = client.post(f"{orchestrator_url.rstrip('/')}/v1/jobs", headers=headers, json=req)
    resp.raise_for_status()
    job = resp.json()

    failures: list[dict[str, Any]] = []
    if case.expect_world:
        failures = [asdict(f) for f in assert_world(case.expect_world, player=player)]

    if case.expect_world and case.expect_world.sandbox_box:
        box = case.expect_world.sandbox_box
        if len(box) == 6:
            clear_box(Box(box[0], box[1], box[2], box[3], box[4], box[5]))

    norm_trace = normalize_tool_calls(job.get("tool_calls") or [])
    return CaseResult(
        case_id=case.id,
        mode="world",
        severity=case.severity.value,
        ok=not failures,
        status=job.get("status") or "",
        steps=int(job.get("steps") or 0),
        model=job.get("model") or "",
        job_id=job.get("job_id"),
        prompt=case.prompt,
        failures=failures,
        trace_hash=_trace_hash(norm_trace),
        trace=norm_trace,
    )


def _maybe_teleport_to_sandbox(case: EvalCase, player: str) -> None:
    """Move eval player into an isolated sandbox region when configured."""

    center = (case.context or {}).get("sandbox_center")
    if not center or len(center) != 3:
        return
    try:
        from agent import tools as T

        x, y, z = int(center[0]), int(center[1]), int(center[2])
        T.teleport_player(player, x, y, z)
    except Exception:
        pass


def _live_player_pos(player: str) -> tuple[float, float, float] | None:
    """Return (x,y,z) of an online player via RCON, or None if unavailable.

    Uses the same RCON path as world probes so world cases see the actual
    coordinates the player is at rather than synthetic case defaults.
    """

    try:
        from agent.eval.world import rcon
        import re

        out = rcon(f"data get entity {player} Pos") or ""
        m = re.search(r"\[([-\d.]+)d?,\s*([-\d.]+)d?,\s*([-\d.]+)d?\]", out)
        if not m:
            return None
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    except Exception:
        return None


def _trace_hash(trace: list[dict[str, Any]]) -> str:
    import hashlib

    canonical = [
        {"name": tc.get("name"), "arguments": tc.get("arguments") or {}}
        for tc in trace
    ]
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_baseline(path: Path, payload: dict[str, Any]) -> None:
    cases = {
        r["case_id"]: {
            "ok": r["ok"],
            "status": r["status"],
            "steps": r["steps"],
            "trace_hash": r.get("trace_hash"),
        }
        for r in payload["results"]
    }
    baseline = {
        "schema_version": 1,
        "tools_version": TOOLS_VERSION,
        "tools_schema_version": TOOLS_SCHEMA_VERSION,
        "provenance": payload["manifest"],
        "cases": cases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True), encoding="utf-8")


def compare_to_baseline(
    results: list[CaseResult],
    baseline_path: Path,
    *,
    cases_by_id: dict[str, EvalCase] | None = None,
) -> dict[str, Any]:
    if not baseline_path.exists():
        return {"baseline": str(baseline_path), "regressions": [], "improvements": [], "drift": []}
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected_cases = baseline.get("cases") or {}
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []
    for r in results:
        old = expected_cases.get(r.case_id)
        if not old:
            continue
        if old.get("ok") and not r.ok:
            regressions.append({"case_id": r.case_id, "from": "pass", "to": "fail"})
        if not old.get("ok") and r.ok:
            improvements.append({"case_id": r.case_id, "from": "fail", "to": "pass"})
        if old.get("trace_hash") and r.trace_hash and old["trace_hash"] != r.trace_hash:
            drift.append({"case_id": r.case_id, "kind": "trace_hash"})
            fail_on_drift = os.environ.get("AGENT_EVAL_FAIL_ON_DRIFT", "0") == "1"
            case_def = (cases_by_id or {}).get(r.case_id)
            if fail_on_drift and case_def and case_def.determinism == "strict":
                regressions.append(
                    {
                        "case_id": r.case_id,
                        "from": f"trace_hash={old['trace_hash'][:12]}",
                        "to": f"trace_hash={r.trace_hash[:12]}",
                    }
                )
        if old.get("steps") is not None and r.steps > int(old["steps"]) + 2:
            regressions.append(
                {
                    "case_id": r.case_id,
                    "from": f"steps={old['steps']}",
                    "to": f"steps={r.steps}",
                }
            )
    return {
        "baseline": str(baseline_path),
        "regressions": regressions,
        "improvements": improvements,
        "drift": drift,
    }


