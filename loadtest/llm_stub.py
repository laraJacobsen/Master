#!/usr/bin/env python3
"""Fake OpenAI-compatible chat-completions endpoint for --llm stub runs.

The backend is pointed here with IDUN_BASE_URL=http://127.0.0.1:<port>/v1 and a
dummy IDUN_API_KEY, so the Label call in backend/aggregation.py runs its real
code path (request, JSON parse, validation, cache) with a fixed fake latency
instead of a real model. No app code changes.

Every call is logged with its start/end time and a hash of the prompt, so the
run can tell apart:
  - distinct prompts (a label the dashboard actually needed), and
  - repeats of an identical prompt, either while an identical call is still in
    flight (two overlapping dashboard polls asking at once) or after one
    finished (the cache key changed but the snippets shown did not).

  GET /stats  -> {"calls": [...]}  (all calls so far)

Run: python loadtest/llm_stub.py --port 8299 --latency 2.0
"""

import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STUB_MARKER = "[stub]"

_lock = threading.Lock()
_calls = []  # dicts: t_start, t_end (unix seconds), prompt_sha, in_flight_at_start


def make_handler(latency_s: float):
    in_flight = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the run's log clean
            pass

        def _send(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/stats":
                with _lock:
                    self._send(200, {"calls": list(_calls)})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self.path.endswith("/chat/completions"):
                self._send(404, {"error": "not found"})
                return
            t_start = time.time()
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            # The user message holds the reference solution + snippets: identical
            # text means an identical question to the model.
            user = next((m["content"] for m in body.get("messages", []) if m.get("role") == "user"), "")
            sha = hashlib.sha256(user.encode()).hexdigest()[:16]
            with _lock:
                in_flight["n"] += 1
                concurrent = in_flight["n"]
            try:
                time.sleep(latency_s)
            finally:
                with _lock:
                    in_flight["n"] -= 1
            point = f"{STUB_MARKER} The students share pattern {sha[:6]}."
            with _lock:
                _calls.append(
                    {"t_start": t_start, "t_end": time.time(), "prompt_sha": sha, "in_flight_at_start": concurrent}
                )
            self._send(
                200,
                {
                    "id": "stub",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps({"discussion_point": point})},
                        }
                    ],
                },
            )

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8299)
    ap.add_argument("--latency", type=float, default=2.0, help="seconds per call (fixed)")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.latency))
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
