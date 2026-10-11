#!/usr/bin/env python3
"""Local review tool: serves review.html and autosaves to the review file.

    python scripts/review.py poe
    python scripts/review.py poe --port 9000 --no-browser

Standard library only. The page talks to this process over three tiny
endpoints, so every approve, reject, split or merge is written to
library/<poet>/review.json straight away. Close the tab whenever you like.
"""

import argparse
import json
import sys
import threading
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ROOT, load_json, poet_dir, read_lines, save_json,  # noqa: E402
                    tokenize_line)

HTML = Path(__file__).resolve().parent / "review.html"


class State:
    def __init__(self, poet: str):
        self.poet = poet
        self.path = poet_dir(poet) / "review.json"
        if not self.path.exists():
            raise SystemExit(f"no review file at {self.path}; run propose.py first")
        self.review = load_json(self.path)
        self.pairs: Counter = Counter()
        clean = self.review.get("clean_text")
        clean_path = (ROOT / clean) if clean else None
        if clean_path and clean_path.exists():
            for line in read_lines(clean_path):
                toks = tokenize_line(line)
                for a, b in zip(toks, toks[1:]):
                    self.pairs[(a, b)] += 1
        self.lock = threading.Lock()

    def save(self, review: dict) -> None:
        with self.lock:
            self.review = review
            save_json(self.path, review)


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self._json({"poet": state.poet, "review": state.review,
                            "have_corpus": bool(state.pairs)})
            elif url.path == "/api/pair":
                q = parse_qs(url.query)
                a = q.get("a", [""])[0].lower().strip()
                b = q.get("b", [""])[0].lower().strip()
                self._json({"count": state.pairs.get((a, b), 0)})
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            if url.path != "/api/save":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            try:
                review = json.loads(body)
            except json.JSONDecodeError:
                self._json({"ok": False, "error": "bad json"}, 400)
                return
            state.save(review)
            self._json({"ok": True})

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poet")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    state = State(args.poet)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"reviewing {state.path}")
    print(f"open {url}  (Ctrl+C to stop; every action is saved immediately)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
