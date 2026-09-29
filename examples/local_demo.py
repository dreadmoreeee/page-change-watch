"""Local demo of a detected change, no internet needed.

Serves a small pricing page on 127.0.0.1 (random free port), then runs
page-change-watch three times:

  1. baseline                          -> new, exit 0
  2. only noise changed                -> unchanged, exit 0
     (timestamp, CSRF token, nav, footer, script, cache-busting query)
  3. the Pro price changed $19 -> $24  -> changed, exit 1

Writes examples/sample-report.md and examples/sample-diff.html.

    python examples/local_demo.py
"""

import json
import os
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from page_change_watch.cli import main  # noqa: E402

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Acme pricing</title>
<link rel="stylesheet" href="/style.css?v={build}"><script src="/app.js?v={build}"></script></head>
<body>
<header><a href="/">Acme</a> {banner}</header>
<nav><a href="/">Home</a> <a href="/blog">Blog</a></nav>
<main>
  <h1>Pricing</h1>
  <p>Prices checked {stamp}. Updated {ago}.</p>
  <form method="post"><input type="hidden" name="csrf_token" value="{token}"></form>
  <table>
    <tr><th>Plan</th><th>Price</th></tr>
    <tr><td>Starter</td><td>$9 per month</td></tr>
    <tr><td>Pro</td><td>{price} per month</td></tr>
    <tr><td>Team</td><td>$49 per month</td></tr>
  </table>
  <p>Session token: {token}</p>
  <script>window.__STATE__ = {{"nonce": "{token}", "build": {build}}};</script>
</main>
<footer>Page generated at {stamp} &middot; build {build}</footer>
</body></html>
"""

VERSIONS = [
    dict(price="$19", stamp="2026-09-29 09:00:00 UTC", ago="2 minutes ago",
         token="k3J9sQ2mW8xZ4vB7nR1tY6pL", build=1001, banner=""),
    dict(price="$19", stamp="2026-09-29 09:05:41 UTC", ago="7 minutes ago",
         token="Z8pQ1wE4rT7yU2iO5aS9dF3g", build=1002, banner="<b>Free shipping this week!</b>"),
    dict(price="$24", stamp="2026-09-29 09:11:03 UTC", ago="just now",
         token="M2nB5vC8xZ1aS4dF7gH0jK3l", build=1003, banner=""),
]


def serve(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/robots.txt":
                body = "User-agent: *\nDisallow: /admin\n"
                ctype = "text/plain"
            else:
                body = PAGE.format(**VERSIONS[state["version"]])
                ctype = "text/html; charset=utf-8"
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main_demo():
    state = {"version": 0}
    server = serve(state)
    url = "http://127.0.0.1:%d/pricing" % server.server_address[1]
    store = HERE / ".local-demo-store"
    shutil.rmtree(store, ignore_errors=True)
    config = store / "watch.json"
    store.mkdir(parents=True)
    config.write_text(json.dumps({"pages": [{"name": "acme-pricing", "url": url}]}), encoding="utf-8")
    base = ["run", "-c", str(config), "--store", str(store), "--delay", "0"]
    try:
        for version, label in enumerate(("baseline", "noise only", "price change")):
            state["version"] = version
            print("=== run %d: %s" % (version + 1, label))
            extra = []
            if version == 2:
                for old in HERE.glob("sample-diff*.html"):
                    old.unlink()
                extra = ["--output", str(HERE / "sample-report.md"), "--html", str(store / "html")]
            code = main(base + extra)
            if version == 2:
                print((HERE / "sample-report.md").read_text(encoding="utf-8"))
                page = next((store / "html").glob("*.html"))
                shutil.copy(page, HERE / "sample-diff.html")
            print("exit code: %d\n" % code)
    finally:
        server.shutdown()
    # make the committed sample independent of the random local port
    for name in ("sample-report.md", "sample-diff.html"):
        path = HERE / name
        path.write_text(path.read_text(encoding="utf-8").replace(url, "http://127.0.0.1:PORT/pricing")
                        .replace(str(store / "html") + os.sep, "html/"), encoding="utf-8")


if __name__ == "__main__":
    main_demo()
