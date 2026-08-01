#!/usr/bin/env python3
"""
Generate a printable invite sheet with your playit.gg connect addresses.

By default, this script reads your existing PLAYIT_SECRET_KEY from .env (or the
environment) and queries the playit API for tunnel addresses, so guests can
join without you copy-pasting anything.

Examples
--------
  # Auto-discover from playit API using PLAYIT_SECRET_KEY in .env:
  ./scripts/print_invite.py

  # Override addresses manually (no API call):
  ./scripts/print_invite.py --java regular-nbc.gl.joinmc.link \\
                            --bedrock levels-tartly.gl.at.ply.gg:4116

  # Choose where to write the sheet:
  ./scripts/print_invite.py --out ~/Desktop/neighborhood-invite.html

Open the resulting HTML in a browser and print it (or "Save as PDF") for a
clean one-page handout. Bedrock players must enter the host and port in
separate fields — the sheet shows both.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from html import escape
from typing import Optional


PLAYIT_API_URL = "https://api.playit.gg/v1/tunnels/list"


def _load_env_file(path: pathlib.Path) -> None:
    """Lightweight .env loader (no python-dotenv dependency)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _fetch_tunnels_urllib(agent_secret: str, timeout: float = 10.0) -> str:
    """Fetch using Python stdlib. May fail on macOS Python without certs."""
    req = urllib.request.Request(
        PLAYIT_API_URL,
        data=b"{}",
        headers={
            "Authorization": f"agent-key {agent_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "neighborhood-server-invite/1.0",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8")


def _fetch_tunnels_curl(agent_secret: str, timeout: float = 10.0) -> str:
    """Fallback: use curl, which trusts the system cert store."""
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found and Python SSL trust store is unusable")
    result = subprocess.run(
        [
            curl, "-sS", "--fail", "--max-time", str(int(timeout)),
            "-X", "POST", PLAYIT_API_URL,
            "-H", f"Authorization: agent-key {agent_secret}",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json",
            "-H", "User-Agent: neighborhood-server-invite/1.0",
            "-d", "{}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _fetch_tunnels(agent_secret: str, timeout: float = 10.0) -> list[dict]:
    try:
        body = _fetch_tunnels_urllib(agent_secret, timeout=timeout)
    except (urllib.error.URLError, ssl.SSLError) as ssl_err:
        # Python on macOS commonly ships without a usable CA bundle. Fall back
        # to curl, which uses the system trust store.
        try:
            body = _fetch_tunnels_curl(agent_secret, timeout=timeout)
        except subprocess.CalledProcessError as curl_err:
            raise RuntimeError(
                f"playit API call failed via curl: {curl_err.stderr.strip() or curl_err}"
            ) from curl_err
    payload = json.loads(body)
    if payload.get("status") != "success":
        raise RuntimeError(f"playit API returned status={payload.get('status')!r}: {body[:200]}")
    return payload["data"]["tunnels"]


def _pick_address(tunnel: dict, prefer_friendly: bool = True) -> Optional[str]:
    """Pick the friendliest address from a tunnel's connect_addresses.

    Preference order (when prefer_friendly):
      1. *.joinmc.link  (clean MC hostname)
      2. *.gl.at.ply.gg (default friendly playit hostname)
      3. anything else  (raw IPs, IPv6)
    """
    candidates = []
    for entry in tunnel.get("connect_addresses", []) or []:
        addr = entry.get("value", {}).get("address")
        if addr:
            candidates.append(addr)

    if not candidates:
        return None

    if prefer_friendly:
        for addr in candidates:
            if "joinmc.link" in addr:
                return addr
        for addr in candidates:
            if "gl.at.ply.gg" in addr:
                return addr
    return candidates[0]


def _split_host_port(address: str, default_port: Optional[int] = None) -> tuple[str, Optional[int]]:
    """Split 'host:port' into (host, port). IPv6 in brackets supported."""
    m = re.fullmatch(r"\[(?P<host>[^\]]+)\](?::(?P<port>\d+))?", address)
    if m:
        return m.group("host"), int(m.group("port")) if m.group("port") else default_port
    if ":" in address and address.count(":") == 1:
        host, port_s = address.rsplit(":", 1)
        if port_s.isdigit():
            return host, int(port_s)
    return address, default_port


def _discover_addresses(secret: str) -> dict[str, str]:
    """Return {'java': 'host[:port]', 'bedrock': 'host:port'} from playit API."""
    tunnels = _fetch_tunnels(secret)
    out: dict[str, str] = {}
    for tunnel in tunnels:
        if not tunnel.get("user_enabled", True) or tunnel.get("disabled_by_admin"):
            continue
        ttype = tunnel.get("tunnel_type", "")
        addr = _pick_address(tunnel)
        if not addr:
            continue
        if "java" in ttype and "java" not in out:
            out["java"] = addr
        elif "bedrock" in ttype and "bedrock" not in out:
            out["bedrock"] = addr
    return out


def _render_html(*, java: Optional[str], bedrock: Optional[str], server_name: str, footer_note: str) -> str:
    """Render a self-contained, print-friendly invite sheet."""

    java_host, java_port = _split_host_port(java, default_port=25565) if java else (None, None)
    bedrock_host, bedrock_port = _split_host_port(bedrock, default_port=19132) if bedrock else (None, None)

    def card(label: str, color: str, edition_logo: str, host: Optional[str], port: Optional[int],
             join_steps: list[str], note: str) -> str:
        if not host:
            host_block = f"<div class=\"address-missing\">No {label} tunnel configured</div>"
        else:
            host_len = len(host)
            host_class = "value-host" + (" tight" if host_len > 22 else "")
            host_block = (
                "<div class=\"address-row\">"
                "<div class=\"label\">Server Address</div>"
                f"<div class=\"{host_class}\">{escape(host)}</div>"
                "</div>"
            )
            if port is not None:
                host_block += (
                    "<div class=\"address-row\">"
                    "<div class=\"label\">Port</div>"
                    f"<div class=\"value-port\">{port}</div>"
                    "</div>"
                )
        steps_html = "".join(f"<li>{escape(step)}</li>" for step in join_steps)
        return f"""
        <section class="card" style="--accent: {color};">
            <header class="card-header">
                <div class="edition-mark">{edition_logo}</div>
                <h2>{escape(label)} Edition</h2>
            </header>
            <div class="address">{host_block}</div>
            <ol class="steps">{steps_html}</ol>
            <p class="note">{escape(note)}</p>
        </section>
        """

    java_steps = [
        "Open Minecraft Java Edition.",
        "Multiplayer  →  Add Server.",
        "Name it anything (e.g. \"Neighborhood\").",
        "Paste the address into Server Address.",
        "Done → Join Server.",
    ]
    bedrock_steps = [
        "Open Minecraft Bedrock Edition.",
        "Play  →  Servers tab  →  Add Server.",
        "Name: Neighborhood.",
        "Enter Server Address and Port from above.",
        "Save → Play.",
    ]

    java_card = card(
        label="Java",
        color="#2e7d32",
        edition_logo="J",
        host=java_host,
        port=java_port,
        join_steps=java_steps,
        note="Cross-platform Java edition (PC / Mac / Linux).",
    )
    bedrock_card = card(
        label="Bedrock",
        color="#1565c0",
        edition_logo="B",
        host=bedrock_host,
        port=bedrock_port,
        join_steps=bedrock_steps,
        note="Bedrock players: phones, tablets, Xbox, PlayStation, Switch, Windows 10/11.",
    )

    generated = datetime.now().strftime("%A, %B %-d %Y · %-I:%M %p")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(server_name)} — Join Sheet</title>
<style>
    :root {{
        --bg: #fafaf6;
        --ink: #1c1f1a;
        --muted: #6b6f63;
        --rule: #d6d8cf;
        --grass: #4b8a3a;
        --dirt: #7a4f31;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
        margin: 0;
        padding: 0;
        background: var(--bg);
        color: var(--ink);
        font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-feature-settings: "ss01", "cv11";
        -webkit-font-smoothing: antialiased;
    }}
    .page {{
        width: 8.5in;
        min-height: 11in;
        margin: 24px auto;
        padding: 0.6in 0.55in 0.5in 0.55in;
        background: white;
        box-shadow: 0 6px 28px rgba(0,0,0,0.08);
        position: relative;
    }}
    header.banner {{
        text-align: center;
        margin-bottom: 28px;
    }}
    .pretitle {{
        text-transform: uppercase;
        letter-spacing: 0.22em;
        font-size: 11px;
        color: var(--muted);
    }}
    h1 {{
        margin: 6px 0 4px 0;
        font-size: 44px;
        letter-spacing: -0.02em;
    }}
    .subtitle {{
        color: var(--muted);
        font-size: 14px;
    }}
    .grass-rule {{
        margin: 18px auto 28px auto;
        height: 14px;
        width: 100%;
        background:
            linear-gradient(var(--grass), var(--grass)) top / 100% 5px no-repeat,
            linear-gradient(var(--dirt), var(--dirt)) bottom / 100% 9px no-repeat;
        border-radius: 2px;
        opacity: 0.85;
    }}
    .cards {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 22px;
    }}
    .card {{
        border: 2px solid var(--accent);
        border-radius: 12px;
        padding: 18px 18px 16px 18px;
        background: white;
        position: relative;
    }}
    .card-header {{
        display: flex;
        align-items: center;
        gap: 12px;
        border-bottom: 1px solid var(--rule);
        padding-bottom: 10px;
        margin-bottom: 14px;
    }}
    .edition-mark {{
        width: 38px;
        height: 38px;
        border-radius: 8px;
        background: var(--accent);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        font-size: 20px;
        letter-spacing: 0;
    }}
    .card h2 {{
        margin: 0;
        font-size: 22px;
        color: var(--accent);
    }}
    .address {{
        background: #f5f6f0;
        border: 1px dashed var(--rule);
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 14px;
    }}
    .address-row {{
        padding: 6px 0;
    }}
    .address-row + .address-row {{ border-top: 1px dotted var(--rule); }}
    .address-row .label {{
        color: var(--muted);
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        margin-bottom: 2px;
    }}
    .value-host {{
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        font-weight: 700;
        font-size: 17px;
        line-height: 1.2;
        overflow-wrap: anywhere;
        letter-spacing: -0.01em;
    }}
    .value-host.tight {{
        font-size: 15px;
    }}
    .value-port {{
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        font-weight: 700;
        font-size: 18px;
        letter-spacing: 0.02em;
    }}
    .address-missing {{
        font-style: italic;
        color: var(--muted);
        text-align: center;
        padding: 8px 0;
    }}
    .steps {{
        padding-left: 20px;
        margin: 0 0 10px 0;
        font-size: 13.5px;
        line-height: 1.45;
    }}
    .steps li {{ margin: 2px 0; }}
    .note {{
        font-size: 11.5px;
        color: var(--muted);
        margin: 6px 0 0 0;
    }}
    .help {{
        margin-top: 26px;
        padding: 16px 18px;
        background: #f5f6f0;
        border-left: 4px solid var(--grass);
        border-radius: 6px;
    }}
    .help h3 {{
        margin: 0 0 6px 0;
        font-size: 14px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--grass);
    }}
    .help ul {{
        margin: 6px 0 0 0;
        padding-left: 20px;
        font-size: 13px;
        line-height: 1.5;
    }}
    .help code {{
        background: white;
        border: 1px solid var(--rule);
        border-radius: 4px;
        padding: 1px 5px;
        font-size: 12px;
    }}
    footer.foot {{
        position: absolute;
        bottom: 0.35in;
        left: 0;
        right: 0;
        text-align: center;
        color: var(--muted);
        font-size: 10.5px;
    }}
    @media print {{
        html, body {{ background: white; }}
        .page {{
            margin: 0;
            box-shadow: none;
            width: auto;
            min-height: auto;
        }}
    }}
</style>
</head>
<body>
<div class="page">
    <header class="banner">
        <div class="pretitle">You're invited to</div>
        <h1>{escape(server_name)}</h1>
        <div class="subtitle">Crossplay Minecraft server · Java &amp; Bedrock welcome</div>
    </header>

    <div class="grass-rule"></div>

    <div class="cards">
        {java_card}
        {bedrock_card}
    </div>

    <section class="help">
        <h3>While you're in</h3>
        <ul>
            <li>Build mode is on — fly with double-jump (Java) or the fly toggle (Bedrock).</li>
            <li>Need help building? Type <code>/agent build me a small cabin in front of me</code> in chat.</li>
            <li>Bedrock gamertags show up with a leading dot (e.g. <code>.YourGamertag</code>) — that's normal.</li>
            <li>If you get stuck in the floor, type <code>/spawn</code> to teleport back.</li>
        </ul>
    </section>

    <footer class="foot">{escape(footer_note)}  ·  generated {escape(generated)}</footer>
</div>
</body>
</html>
"""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a printable Minecraft invite sheet.")
    parser.add_argument("--java", help="Override Java connect address (host or host:port).")
    parser.add_argument("--bedrock", help="Override Bedrock connect address (host:port).")
    parser.add_argument("--secret", help="Override PLAYIT_SECRET_KEY (defaults to .env / env).")
    parser.add_argument("--out", default=str(pathlib.Path.home() / "Desktop" / "neighborhood-invite.html"),
                        help="Output HTML path (default: ~/Desktop/neighborhood-invite.html).")
    parser.add_argument("--server-name", default="Neighborhood",
                        help="Display name for the server (default: Neighborhood).")
    parser.add_argument("--footer-note", default="neighborhood-server",
                        help="Small footer text.")
    parser.add_argument("--no-api", action="store_true",
                        help="Skip the playit API call (requires --java and/or --bedrock).")
    args = parser.parse_args(argv)

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    _load_env_file(repo_root / ".env")

    java = args.java
    bedrock = args.bedrock

    if not args.no_api and (not java or not bedrock):
        secret = args.secret or os.environ.get("PLAYIT_SECRET_KEY", "").strip()
        if secret:
            try:
                discovered = _discover_addresses(secret)
                java = java or discovered.get("java")
                bedrock = bedrock or discovered.get("bedrock")
                print(f"playit API: java={discovered.get('java')!r} bedrock={discovered.get('bedrock')!r}",
                      file=sys.stderr)
            except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
                print(f"warning: could not query playit API ({e}); falling back to overrides", file=sys.stderr)
        else:
            print("warning: PLAYIT_SECRET_KEY not set; pass --java / --bedrock or set the secret", file=sys.stderr)

    if not java and not bedrock:
        print("error: no addresses available (need API access or --java/--bedrock)", file=sys.stderr)
        return 1

    html = _render_html(
        java=java,
        bedrock=bedrock,
        server_name=args.server_name,
        footer_note=args.footer_note,
    )

    out_path = pathlib.Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
