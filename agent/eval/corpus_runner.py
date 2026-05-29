"""Run the NL corpus end-to-end against live mc-agent + mc-lan."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agent.eval.corpus_assertions import assert_corpus_expect, classify_primary_failure
from agent.eval.corpus_case import CorpusCase
from agent.eval.corpus_loader import filter_corpus_cases, load_corpus
from agent.eval.assertions import normalize_tool_calls
from agent.eval.probes import run_world_probe
from agent.eval.world import Box, clear_box, rcon
from agent.tool_registry import TOOLS_VERSION


@dataclass
class CorpusCaseResult:
    case_id: str
    category: str
    intent: str
    language_style: str
    prompt: str
    ok: bool
    status: str
    steps: int
    model: str
    job_id: str | None
    primary_failure: str
    failures: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    probe_message: str = ""
    sandbox_center: list[int] = field(default_factory=list)
    temperature: float | None = None
    cell_index: int = 0
    latency_ms: int = 0


@dataclass(frozen=True)
class SandboxCell:
    index: int
    center: tuple[int, int, int]
    box: Box


class SandboxGrid:
    """12-column lane starting at (10000, -60, 10000) with 48-block stride."""

    ORIGIN = (10000, -60, 10000)
    COLS = 12
    COL_STRIDE = 48
    ROW_STRIDE = 64

    def __init__(self) -> None:
        self._next = 0

    def allocate(self) -> SandboxCell:
        idx = self._next
        self._next += 1
        col = idx % self.COLS
        row = idx // self.COLS
        cx = self.ORIGIN[0] + col * self.COL_STRIDE
        cy = self.ORIGIN[1]
        cz = self.ORIGIN[2] + row * self.ROW_STRIDE
        pad = 18
        box = Box(cx - pad, cy - 2, cz - pad, cx + pad, cy + 28, cz + pad).normalize()
        return SandboxCell(index=idx, center=(cx, cy, cz), box=box)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _detect_player(repo_root: Path) -> str:
    env_player = os.environ.get("AGENT_CORPUS_PLAYER", "").strip()
    if env_player:
        return env_player
    try:
        from agent import tools as T

        raw = T._rcon("list", timeout=10) or ""
        import re

        m = re.search(r"online:?\s*(.+)$", raw)
        if m:
            first = m.group(1).split(",")[0].strip()
            if first:
                return first
    except Exception:
        pass
    script = repo_root / "scripts" / "_detect_player.sh"
    if script.is_file():
        try:
            out = subprocess.check_output([str(script)], text=True, timeout=15).strip()
            if out:
                return out
        except (subprocess.SubprocessError, OSError):
            pass
    raise RuntimeError(
        "no online player detected. Join the server or set AGENT_CORPUS_PLAYER=<name>"
    )


def _prepare_cell(cell: SandboxCell, player: str) -> None:
    from agent import tools as T

    cx, cy, cz = cell.center
    # Move into the target chunk before clearing it, then restore a small
    # standing pad so the player cannot fall through the cleared sandbox.
    T.teleport_player(player, cx, cy + 1, cz)
    time.sleep(0.2)
    clear_box(cell.box)
    rcon(f"fill {cx - 2} {cy} {cz - 2} {cx + 2} {cy} {cz + 2} grass_block replace", timeout=15)
    T.teleport_player(player, cx, cy + 1, cz)
    T._rcon(f"execute as {T._quote_player(player)} at @s run tp @s ~ ~ ~ 0 0", timeout=15)
    settle = float(os.environ.get("AGENT_CORPUS_SETTLE_SEC", "0.5"))
    deadline = time.monotonic() + max(2.0, settle + 2.0)
    while time.monotonic() < deadline:
        px, py, pz = _live_player_pos(player)
        if abs(px - cx) <= 2 and abs(pz - cz) <= 2 and py >= cy:
            break
        time.sleep(0.2)
    time.sleep(settle)


def _live_player_pos(player: str) -> tuple[float, float, float]:
    from agent.eval.runner import _live_player_pos

    pos = _live_player_pos(player)
    if pos:
        return pos
    cx, cy, cz = SandboxGrid.ORIGIN
    return float(cx), float(cy + 2), float(cz)


def _run_one_case(
    client: httpx.Client,
    *,
    orchestrator_url: str,
    headers: dict[str, str],
    case: CorpusCase,
    player: str,
    cell: SandboxCell,
    model_override: str | None,
    temperature: float | None,
) -> CorpusCaseResult:
    _prepare_cell(cell, player)
    lx, ly, lz = _live_player_pos(player)
    req: dict[str, Any] = {
        "player": player,
        "uuid": str(uuid.uuid4()),
        "x": lx,
        "y": ly,
        "z": lz,
        "prompt": case.prompt,
        "dry_run": False,
        "eval_mode": True,
    }
    if model_override:
        req["eval_model"] = model_override
    if temperature is not None:
        req["eval_temperature"] = temperature

    started = time.perf_counter()
    try:
        resp = client.post(
            f"{orchestrator_url.rstrip('/')}/v1/jobs",
            headers=headers,
            json=req,
            timeout=float(os.environ.get("AGENT_CORPUS_CLIENT_TIMEOUT_SEC", "180")),
        )
        resp.raise_for_status()
        job = resp.json()
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return CorpusCaseResult(
            case_id=case.id,
            category=case.category,
            intent=case.intent,
            language_style=case.language_style,
            prompt=case.prompt,
            ok=False,
            status="error",
            steps=0,
            model="",
            job_id=None,
            primary_failure="timeout",
            failures=[{"kind": "timeout", "message": str(exc)}],
            sandbox_center=list(cell.center),
            temperature=temperature,
            cell_index=cell.index,
            latency_ms=elapsed_ms,
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    tool_calls = job.get("tool_calls") or []
    norm_trace = normalize_tool_calls(tool_calls)
    status = str(job.get("status") or "")
    steps = int(job.get("steps") or 0)
    tool_ok = (
        all((tc.get("result") or {}).get("ok", True) for tc in norm_trace if tc.get("result"))
        if norm_trace
        else False
    )

    probe = run_world_probe(
        case.expect.world_probe,
        player=player,
        sandbox_center=cell.center,
        tool_ok=tool_ok,
        tool_calls=tool_calls,
    )

    failures = assert_corpus_expect(
        case.expect,
        actual_status=status,
        actual_steps=steps,
        tool_calls=tool_calls,
        world_probe_ok=probe.ok,
        world_probe_message=probe.message,
    )
    primary = classify_primary_failure(failures)

    return CorpusCaseResult(
        case_id=case.id,
        category=case.category,
        intent=case.intent,
        language_style=case.language_style,
        prompt=case.prompt,
        ok=not failures,
        status=status,
        steps=steps,
        model=str(job.get("model") or ""),
        job_id=job.get("job_id"),
        primary_failure=primary,
        failures=[asdict(f) for f in failures],
        trace=norm_trace,
        probe_message=probe.message,
        sandbox_center=list(cell.center),
        temperature=temperature,
        cell_index=cell.index,
        latency_ms=elapsed_ms,
    )


def run_corpus(
    *,
    repo_root: Path | None = None,
    orchestrator_url: str | None = None,
    api_token: str | None = None,
    player: str | None = None,
    category: str | None = None,
    case_id: str | None = None,
    limit: int | None = None,
    model_override: str | None = None,
    temperature: float | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or _repo_root()
    if os.environ.get("AGENT_EVAL_ALLOW_WORLD_MUTATION") != "1":
        os.environ["AGENT_EVAL_ALLOW_WORLD_MUTATION"] = "1"

    loaded = load_corpus(root / "agent" / "eval" / "corpus")
    cases = filter_corpus_cases(
        loaded.cases,
        case_id=case_id,
        category=category or os.environ.get("AGENT_CORPUS_CATEGORY") or None,
        limit=limit,
    )
    if not cases:
        raise ValueError("no corpus cases matched filters")

    player_name = player or _detect_player(root)
    url = orchestrator_url or os.environ.get("AGENT_ORCH_URL", "http://127.0.0.1:8787")
    token = api_token or os.environ.get("AGENT_API_TOKEN", "dev-change-me")
    headers = {"Authorization": f"Bearer {token}"}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = output_dir or (root / "data" / "corpus-runs" / ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = SandboxGrid()
    results: list[CorpusCaseResult] = []
    client_timeout = float(os.environ.get("AGENT_CORPUS_CLIENT_TIMEOUT_SEC", "180"))

    with httpx.Client(timeout=client_timeout) as client:
        for case in cases:
            cell = grid.allocate()
            result = _run_one_case(
                client,
                orchestrator_url=url,
                headers=headers,
                case=case,
                player=player_name,
                cell=cell,
                model_override=model_override
                or os.environ.get("AGENT_EVAL_MODEL_OVERRIDE")
                or None,
                temperature=temperature,
            )
            results.append(result)
            clear_box(cell.box)

    envelopes: list[dict[str, Any]] = []
    for r in results:
        envelopes.append(
            {
                "schema_version": 1,
                "tools_version": TOOLS_VERSION,
                "case_id": r.case_id,
                "category": r.category,
                "intent": r.intent,
                "language_style": r.language_style,
                "prompt": r.prompt,
                "ok": r.ok,
                "status": r.status,
                "steps": r.steps,
                "model": r.model,
                "job_id": r.job_id,
                "primary_failure": r.primary_failure,
                "failures": r.failures,
                "trace": r.trace,
                "probe_message": r.probe_message,
                "temperature": r.temperature,
                "sandbox_center": r.sandbox_center,
                "latency_ms": r.latency_ms,
            }
        )

    summary = _summarize(results)
    payload = {
        "timestamp": ts,
        "player": player_name,
        "orchestrator_url": url,
        "tools_version": TOOLS_VERSION,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (out_dir / "envelopes.jsonl").open("w", encoding="utf-8") as ef:
        for env in envelopes:
            ef.write(json.dumps(env, sort_keys=True) + "\n")

    latest = root / "data" / "corpus-runs" / "latest"
    if latest.is_symlink() or latest.exists():
        try:
            latest.unlink()
        except OSError:
            pass
    try:
        latest.symlink_to(out_dir.name, target_is_directory=True)
    except OSError:
        pass

    payload["output_dir"] = str(out_dir)
    return payload


def _summarize(results: list[CorpusCaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.ok)
    by_category: dict[str, dict[str, int]] = {}
    by_failure: dict[str, int] = {}
    latencies: list[int] = []
    for r in results:
        cat = by_category.setdefault(r.category, {"total": 0, "passed": 0})
        cat["total"] += 1
        if r.ok:
            cat["passed"] += 1
        if not r.ok:
            by_failure[r.primary_failure] = by_failure.get(r.primary_failure, 0) + 1
        if r.latency_ms > 0:
            latencies.append(r.latency_ms)
    latency_stats: dict[str, float] = {}
    if latencies:
        sl = sorted(latencies)
        n = len(sl)
        latency_stats = {
            "count": float(n),
            "min_ms": float(sl[0]),
            "p50_ms": float(sl[n // 2]),
            "p90_ms": float(sl[max(0, int(n * 0.9) - 1)]),
            "max_ms": float(sl[-1]),
            "mean_ms": float(sum(sl) / n),
            "total_s": round(sum(sl) / 1000.0, 2),
        }
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_category": by_category,
        "by_failure": by_failure,
        "latency": latency_stats,
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run NL corpus against live server")
    parser.add_argument("--repo-root", default=str(_repo_root()))
    parser.add_argument("--orchestrator-url", default=os.environ.get("AGENT_ORCH_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--api-token", default=os.environ.get("AGENT_API_TOKEN", "dev-change-me"))
    parser.add_argument("--player", default=os.environ.get("AGENT_CORPUS_PLAYER", ""))
    parser.add_argument("--category")
    parser.add_argument("--case")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)

    payload = run_corpus(
        repo_root=Path(args.repo_root).resolve(),
        orchestrator_url=args.orchestrator_url,
        api_token=args.api_token,
        player=args.player or None,
        category=args.category,
        case_id=args.case,
        limit=args.limit,
        model_override=args.model or None,
        temperature=args.temperature,
        output_dir=Path(args.json_out).resolve() if args.json_out else None,
    )
    s = payload["summary"]
    print(
        f"corpus: total={s['total']} passed={s['passed']} failed={s['failed']} "
        f"pass_rate={s['pass_rate']:.1%} out={payload['output_dir']}"
    )
    if s["failed"]:
        min_rate = float(os.environ.get("AGENT_CORPUS_MIN_PASS_RATE", "1.0"))
        if s["pass_rate"] < min_rate:
            raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
