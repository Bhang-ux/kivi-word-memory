"""HTTP integration tests for the demo server.

Spawns the actual server (stdlib http.server, no dependencies) on an
ephemeral port with a temporary DB, and exercises the JSON endpoints
end-to-end the way the UI does.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(url: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.05)
    raise RuntimeError(f"server did not become healthy on {url} within {timeout}s")


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read())


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2) as r:
        return json.loads(r.read())


class ServerContext:
    def __init__(self):
        self.port = _free_port()
        self.db = os.path.join(tempfile.mkdtemp(), "server.db")
        self.env = {**os.environ,
                    "KIVI_PORT": str(self.port),
                    "KIVI_DB":   self.db,
                    "PYTHONUNBUFFERED": "1"}
        self.proc: subprocess.Popen | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(APP_DIR, "app", "server.py")],
            env=self.env, cwd=APP_DIR,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _wait_healthy(self.base + "/api/health")
        return self

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class TestHttpApi(unittest.TestCase):
    def test_health_reports_user_id(self):
        with ServerContext() as ctx:
            h = _get(ctx.base + "/api/health")
            self.assertEqual(h["status"], "ok")
            self.assertEqual(h["user_id"], "default")

    def test_observe_then_rewrite_roundtrip(self):
        with ServerContext() as ctx:
            _post(ctx.base + "/api/observe", {
                "kind": "correction",
                "asr": "ask aditya to review the sarvam kiwi service",
                "formatted": "Ask Aditya to review the Sarvam Kiwi service.",
                "selection": "Aditya", "replacement": "Aaditya", "weight": 2,
            })
            _post(ctx.base + "/api/observe", {
                "kind": "correction",
                "asr": "ask aditya to review the sarvam kiwi service",
                "formatted": "Ask Aditya to review the Sarvam Kiwi service.",
                "selection": "Kiwi", "replacement": "Kivi", "weight": 2,
            })
            r = _post(ctx.base + "/api/rewrite", {
                "formatted": "Ask Aditya to review the Sarvam Kiwi service.",
                "asr": "ask aditya to review the sarvam kiwi service",
            })
            self.assertEqual(r["text"], "Ask Aaditya to review the Sarvam Kivi service.")
            self.assertEqual(len(r["decisions"]), 2)

    def test_bulk_observe(self):
        with ServerContext() as ctx:
            r = _post(ctx.base + "/api/observe/bulk", {"observations": [
                {"kind": "correction",
                 "formatted": "Ping Mehta.", "selection": "Mehta",
                 "replacement": "Mayhta", "weight": 2},
                {"kind": "correction",
                 "formatted": "Ping Kumar.", "selection": "Kumar",
                 "replacement": "Kuumar", "weight": 2},
            ]})
            self.assertEqual(r["count"], 2)
            self.assertTrue(all(x["accepted"] for x in r["results"]))
            m = _get(ctx.base + "/api/memory")
            words = {w["word"] for w in m["words"]}
            self.assertEqual(words, {"mayhta", "kuumar"})

    def test_reset_requires_confirm(self):
        with ServerContext() as ctx:
            _post(ctx.base + "/api/seed", {})
            self.assertTrue(_get(ctx.base + "/api/memory")["words"])
            # Missing confirm should refuse.
            try:
                _post(ctx.base + "/api/reset", {})
                self.fail("expected HTTP 400")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 400)
            # With confirm, wipes.
            _post(ctx.base + "/api/reset", {"confirm": True})
            self.assertEqual(_get(ctx.base + "/api/memory")["words"], [])

    def test_sweep_endpoint(self):
        with ServerContext() as ctx:
            _post(ctx.base + "/api/observe", {
                "kind": "correction",
                "formatted": "Ping Mehta.", "selection": "Mehta",
                "replacement": "Mayhta", "weight": 1,
            })
            # ttl_days=0 forces even a fresh candidate to be considered stale.
            r = _post(ctx.base + "/api/sweep", {"ttl_days": 0})
            self.assertEqual(r["removed"], ["mayhta"])


if __name__ == "__main__":
    unittest.main()
