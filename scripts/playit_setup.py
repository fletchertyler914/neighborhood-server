#!/usr/bin/env python3
"""
Idempotently create the standard Minecraft tunnels for this server in playit.gg.

What it does
------------
1. Reads ``PLAYIT_SECRET_KEY`` from ``.env`` (or the environment).
2. Asks playit which tunnels already exist for that agent.
3. For each of (Minecraft Java TCP 25565) and (Minecraft Bedrock UDP 19132)
   that is *missing*, creates it via the official playit API.
4. Prints the final connect addresses guests should use.

What it does NOT do
-------------------
- Sign up for a playit.gg account.
- Register a new agent / mint a new ``PLAYIT_SECRET_KEY``.
  Those steps require the browser-based claim flow at https://playit.gg.
  When ``PLAYIT_SECRET_KEY`` is missing, this script tells you how to
  produce one and exits.

Run
---
::

    ./scripts/playit_setup.py            # auto-create both standard tunnels
    ./scripts/playit_setup.py --list     # just show what already exists
    ./scripts/playit_setup.py --dry-run  # show what would be created

After running, ``./scripts/print_invite.py`` will discover the new addresses.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional


PLAYIT_API_BASE = "https://api.playit.gg"


# --- desired tunnels -------------------------------------------------------

# Each entry describes one tunnel we want to exist for a Minecraft server.
DESIRED_TUNNELS = [
    {
        "name": "Minecraft Java",
        "tunnel_type": "minecraft-java",
        "local_port": 25565,
        "icon": "Java",
    },
    {
        "name": "Minecraft Bedrock",
        "tunnel_type": "minecraft-bedrock",
        "local_port": 19132,
        "icon": "Bedrock",
    },
]

DEFAULT_LOCAL_IP = "127.0.0.1"
DEFAULT_REGION = "global"


# --- env loader (no python-dotenv dep) -------------------------------------


def _load_env_file(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --- HTTP -------------------------------------------------------------------


def _request_urllib(path: str, body: dict, secret: str, timeout: float = 15.0) -> str:
    req = urllib.request.Request(
        f"{PLAYIT_API_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"agent-key {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "neighborhood-server-playit-setup/1.0",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8")


def _request_curl(path: str, body: dict, secret: str, timeout: float = 15.0) -> str:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found and Python SSL trust store is unusable")
    result = subprocess.run(
        [
            curl, "-sS", "--fail-with-body", "--max-time", str(int(timeout)),
            "-X", "POST", f"{PLAYIT_API_BASE}{path}",
            "-H", f"Authorization: agent-key {secret}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json",
            "-H", "User-Agent: neighborhood-server-playit-setup/1.0",
            "-d", json.dumps(body),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _api_call(path: str, body: dict, secret: str) -> dict:
    try:
        raw = _request_urllib(path, body, secret)
    except (urllib.error.URLError, ssl.SSLError):
        try:
            raw = _request_curl(path, body, secret)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            raise RuntimeError(
                f"playit API {path} failed: {stderr or stdout or e}"
            ) from e
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"playit API {path} returned non-JSON: {raw[:200]}") from e
    if payload.get("status") != "success":
        raise RuntimeError(f"playit API {path} returned {payload.get('status')!r}: {raw[:400]}")
    return payload.get("data", {})


# --- domain helpers --------------------------------------------------------


def _pick_address(tunnel: dict) -> Optional[str]:
    candidates = []
    for entry in tunnel.get("connect_addresses", []) or []:
        addr = entry.get("value", {}).get("address")
        if addr:
            candidates.append(addr)
    if not candidates:
        return None
    for addr in candidates:
        if "joinmc.link" in addr:
            return addr
    for addr in candidates:
        if "gl.at.ply.gg" in addr:
            return addr
    return candidates[0]


def _summarize_tunnel(tunnel: dict) -> str:
    name = tunnel.get("name", "?")
    ttype = tunnel.get("tunnel_type", "?")
    addr = _pick_address(tunnel) or "(no address yet)"
    enabled = "on" if tunnel.get("user_enabled", True) and not tunnel.get("disabled_by_admin") else "off"
    return f"{name:<22} {ttype:<20} {addr:<40} {enabled}"


# --- main logic ------------------------------------------------------------


def list_tunnels(secret: str) -> list[dict]:
    return _api_call("/v1/tunnels/list", {}, secret).get("tunnels", []) or []


def _existing_match(existing: list[dict], desired: dict) -> Optional[dict]:
    """Return an existing tunnel that satisfies `desired`, else None.

    A tunnel matches when it has the same tunnel_type and its local_port
    config matches the desired port (so we don't accidentally re-create a
    user's customized tunnel).
    """
    for tun in existing:
        if tun.get("tunnel_type") != desired["tunnel_type"]:
            continue
        origin = tun.get("origin", {}) or {}
        if origin.get("type") != "agent":
            continue
        details = origin.get("details", {}) or {}
        fields = (details.get("config_data", {}) or {}).get("fields", []) or []
        port = None
        for f in fields:
            if f.get("name") == "local_port":
                try:
                    port = int(f.get("value", ""))
                except (TypeError, ValueError):
                    port = None
        if port == desired["local_port"]:
            return tun
    return None


def create_tunnel(secret: str, desired: dict, region: str = DEFAULT_REGION,
                  local_ip: str = DEFAULT_LOCAL_IP) -> dict:
    body = {
        "name": desired["name"],
        "protocol": {"type": "tunnel-type", "details": desired["tunnel_type"]},
        "origin": {
            "type": "agent",
            "data": {
                "agent_id": None,
                "config": {
                    "fields": [
                        {"name": "local_ip", "value": local_ip},
                        {"name": "local_port", "value": str(desired["local_port"])},
                    ]
                },
            },
        },
        "endpoint": {"type": "region", "details": {"region": region}},
        "enabled": True,
    }
    return _api_call("/v1/tunnels/create", body, secret)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotently set up playit tunnels for this server.")
    parser.add_argument("--secret", help="Override PLAYIT_SECRET_KEY (defaults to .env / env).")
    parser.add_argument("--region", default=DEFAULT_REGION,
                        help="playit region for new tunnels (default: global).")
    parser.add_argument("--local-ip", default=DEFAULT_LOCAL_IP,
                        help="Local IP that playit forwards to (default: 127.0.0.1).")
    parser.add_argument("--list", action="store_true", help="Just list existing tunnels and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without creating tunnels.")
    args = parser.parse_args(argv)

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    _load_env_file(repo_root / ".env")

    secret = args.secret or os.environ.get("PLAYIT_SECRET_KEY", "").strip()
    if not secret:
        print("PLAYIT_SECRET_KEY is not set. To get one:", file=sys.stderr)
        print("  1. Sign up at https://playit.gg/login", file=sys.stderr)
        print("  2. Create an agent: https://playit.gg/account/agents", file=sys.stderr)
        print("     → 'Download for Docker' → copy the secret key.", file=sys.stderr)
        print("  3. Paste it into .env as PLAYIT_SECRET_KEY=pit-...", file=sys.stderr)
        print("  4. Re-run: ./scripts/playit_setup.py", file=sys.stderr)
        return 2

    try:
        existing = list_tunnels(secret)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Found {len(existing)} existing tunnel(s):")
    if not existing:
        print("  (none)")
    for tun in existing:
        print(f"  · {_summarize_tunnel(tun)}")

    if args.list:
        return 0

    print()
    created = 0
    skipped = 0
    for desired in DESIRED_TUNNELS:
        match = _existing_match(existing, desired)
        if match:
            addr = _pick_address(match) or "(no address yet)"
            print(f"= {desired['icon']:<8} already exists  → {addr}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"+ {desired['icon']:<8} would create   → {desired['name']} ({desired['tunnel_type']}, local_port={desired['local_port']}, region={args.region})")
            continue
        try:
            create_tunnel(secret, desired, region=args.region, local_ip=args.local_ip)
            created += 1
            print(f"+ {desired['icon']:<8} created        → {desired['name']} ({desired['tunnel_type']}, local_port={desired['local_port']}, region={args.region})")
        except RuntimeError as e:
            print(f"! {desired['icon']:<8} create failed  → {e}", file=sys.stderr)

    if created:
        print()
        print("Re-querying playit for new addresses...")
        try:
            existing = list_tunnels(secret)
        except RuntimeError as e:
            print(f"warning: refresh failed ({e}); the tunnels were created — check the playit dashboard", file=sys.stderr)
            return 0
        print()
        for tun in existing:
            print(f"  · {_summarize_tunnel(tun)}")

    print()
    print(f"Summary: {created} created, {skipped} already existed.")
    if created and not args.dry_run:
        print("Tip: regenerate the printable invite with: ./scripts/print_invite.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
