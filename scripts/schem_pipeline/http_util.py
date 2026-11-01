"""Shared HTTP helpers: UA, rate limit, robots.txt cache."""

from __future__ import annotations

import threading
import time
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

USER_AGENT_DEFAULT = (
    "NeighborhoodSchemPipeline/1.0 (+https://github.com/neighborhood-server; "
    "curated gap fill; respects robots.txt)"
)


class RateLimitedSession:
    def __init__(
        self,
        *,
        user_agent: str,
        rate_limit_seconds: float = 1.5,
        timeout: float = 45.0,
        respect_robots: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._lock = threading.Lock()
        self._last_by_host: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last_by_host.get(host, 0.0)
            delay = self.rate_limit_seconds - (now - last)
            if delay > 0:
                time.sleep(delay)
            self._last_by_host[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                self._wait(host)
                rp.set_url(robots_url)
                rp.read()
                self._robots[host] = rp
            except Exception:
                # Fail open for fetch of robots itself; still rate-limit.
                self._robots[host] = None
                return True
        rp = self._robots.get(host)
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def get_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> tuple[bytes, str, str]:
        """GET → (body, final_url, content_type)."""
        if not self._allowed(url):
            raise PermissionError(f"robots.txt disallows: {url}")
        host = urlparse(url).netloc.lower()
        self._wait(host)
        hdrs = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        try:
            import httpx

            with httpx.Client(follow_redirects=True, timeout=self.timeout, headers=hdrs) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.content, str(resp.url), resp.headers.get("content-type", "")
        except Exception:
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                path = Path(tmp.name)
            try:
                cmd = [
                    "curl",
                    "-fsSL",
                    "-A",
                    self.user_agent,
                    "-o",
                    str(path),
                    "-w",
                    "%{url_effective}\n%{content_type}",
                    url,
                ]
                for k, v in hdrs.items():
                    if k.lower() == "user-agent":
                        continue
                    cmd[1:1] = ["-H", f"{k}: {v}"]
                proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"download failed ({proc.returncode}): {url}\n{(proc.stderr or '').strip()}"
                    )
                meta = (proc.stdout or "").strip().splitlines()
                final = meta[0] if meta else url
                ctype = meta[1] if len(meta) > 1 else ""
                return path.read_bytes(), final, ctype
            finally:
                path.unlink(missing_ok=True)

    def get_json(self, url: str) -> Any:
        body, _, _ = self.get_bytes(url, headers={"Accept": "application/json"})
        import json

        return json.loads(body.decode("utf-8"))
