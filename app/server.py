"""Zero-dependency demonstration API + UI server for Kivi word memory.

Runs on the Python standard library only -- no ``pip install`` required.

Endpoints
---------
  GET  /                       demonstration UI
  GET  /api/health             liveness + db size + user id
  GET  /api/memory             full inspectable memory state
  GET  /api/events             audit trail

  POST /api/observe            feed an observation
                                 (correction | confirm | edit | delete)
  POST /api/observe/bulk       apply many observations at once (JSONL body)
  POST /api/rewrite            formatted (+ optional asr) -> memory-aware
  POST /api/suppress           silence a word (never rewritten again)
  POST /api/delete             forget a word
  POST /api/sweep              drop un-reinforced candidates (>= TTL days)
  POST /api/reset              wipe memory and re-apply migrations
  POST /api/seed               load the canonical seed observations

Environment
-----------
  KIVI_PORT  (default 8000)
  KIVI_DB    (default db/kivi.db under the repo root)

Run:  python3 app/server.py
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "app"))

from engine import Engine  # noqa: E402
from store import Store  # noqa: E402

PORT = int(os.environ.get("KIVI_PORT", "8000"))
store = Store()
store.migrate()
engine = Engine(store)


class Handler(BaseHTTPRequestHandler):
    server_version = "KiviWordMemory/1.0"

    # -- helpers -------------------------------------------------------------
    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def _static(self, rel: str) -> None:
        path = os.path.normpath(os.path.join(APP_DIR, "static", rel))
        if not path.startswith(os.path.join(APP_DIR, "static")) or not os.path.isfile(path):
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(path)[0] or "text/plain"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # keep stdout readable
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    # -- routes --------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route in ("/", "/index.html"):
            self._static("index.html")
        elif route == "/api/memory":
            self._json(200, store.snapshot())
        elif route == "/api/events":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["100"])[0])
            rows = store.events(limit=limit)
            self._json(200, [
                {"kind": r["kind"], "payload": json.loads(r["payload"]), "at": r["at"]}
                for r in rows
            ])
        elif route == "/api/health":
            self._json(200, {
                "status": "ok",
                "user_id": store.user_id,
                "db_bytes": store.db_size_bytes(),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            data = self._body()
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid JSON"})

        if route == "/api/observe":
            r = engine.observe(
                kind=str(data.get("kind", "")),
                asr=str(data.get("asr", "")),
                formatted=str(data.get("formatted", "")),
                selection=str(data.get("selection", "")),
                replacement=str(data.get("replacement", "")),
                app_context=str(data.get("app_context", "")),
                weight=int(data.get("weight", 1)),
            )
            return self._json(200, asdict(r))

        if route == "/api/observe/bulk":
            obs = data.get("observations") or []
            if not isinstance(obs, list):
                return self._json(400, {"error": "observations must be a list"})
            results = []
            for o in obs:
                if not isinstance(o, dict):
                    results.append({"accepted": False, "reason": "not an object"})
                    continue
                r = engine.observe(
                    kind=str(o.get("kind", "")),
                    asr=str(o.get("asr", "")),
                    formatted=str(o.get("formatted", "")),
                    selection=str(o.get("selection", "")),
                    replacement=str(o.get("replacement", "")),
                    app_context=str(o.get("app_context", "")),
                    weight=int(o.get("weight", 1)),
                )
                results.append(asdict(r))
            return self._json(200, {"count": len(results), "results": results})

        if route == "/api/rewrite":
            r = engine.rewrite(str(data.get("formatted", "")), str(data.get("asr", "")))
            payload = asdict(r)
            payload["decisions"] = [asdict(d) for d in r.decisions]
            payload["latency_ms"] = round(r.latency_ms, 3)
            return self._json(200, payload)

        if route == "/api/suppress":
            word = str(data.get("word", "")).lower()
            row = store.get_word(word)
            if row is None:
                return self._json(404, {"error": f"word {word!r} not in memory"})
            engine.suppress(row["id"])
            return self._json(200, {"suppressed": word})

        if route == "/api/delete":
            r = engine.observe(kind="delete", selection=str(data.get("word", "")))
            return self._json(200, asdict(r))

        if route == "/api/sweep":
            ttl = data.get("ttl_days")
            removed = engine.sweep(int(ttl) if ttl is not None else None)
            return self._json(200, {"removed": removed, "count": len(removed)})

        if route == "/api/reset":
            if not data.get("confirm"):
                return self._json(400, {"reset": False, "reason": "confirm=true required"})
            engine.forget_all()
            return self._json(200, {"reset": True})

        if route == "/api/seed":
            from seed import SEEDS
            applied = [asdict(engine.observe(**s)) for s in SEEDS]
            return self._json(200, {"seeded": len(SEEDS), "results": applied})

        self._json(404, {"error": "not found"})


def main() -> None:
    addr = ("127.0.0.1", PORT)
    print(
        f"Kivi word memory demo listening on http://{addr[0]}:{addr[1]}\n"
        f"  db: {store.path} (user: {store.user_id})"
    )
    ThreadingHTTPServer(addr, Handler).serve_forever()


if __name__ == "__main__":
    main()
