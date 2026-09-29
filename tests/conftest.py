import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pricing_page(price="$19", stamp="2026-09-29 10:00:00", token="a8F3kLq9Zx2Wv7Pt5RmN0bYc",
                 nav="Home", script="var build = 1;", cb="v=1001", ago="5 minutes ago",
                 long_date="September 29, 2026 at 10:00 AM", hexhash="9f86d081884c7d659a2feaa0c55ad015"):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Pricing {stamp}</title>
<link rel="stylesheet" href="/style.css?{cb}"><script src="/app.js?{cb}"></script>
<style>.price {{ color: red }}</style></head>
<body>
<header><a href="/">Acme</a> <span>{nav}</span></header>
<nav><a href="/a">{nav}</a> <a href="/b">Blog</a></nav>
<main>
  <h1>Pricing</h1>
  <p>Last updated {stamp}. Posted {ago}.</p>
  <p>Published {long_date}</p>
  <form method="post"><input type="hidden" name="csrf_token" value="{token}"></form>
  <p>Session token: {token}</p>
  <p>Asset: /img/logo.png?{cb} build {hexhash}</p>
  <div class="plan"><span class="name">Pro</span> <span class="price">{price}</span> per month</div>
  <div class="plan"><span class="name">Team</span> <span class="price">$49</span> per month</div>
  <aside>Related: {nav}</aside>
  <script>window.nonce = "{token}"; {script}</script>
  <p class="visitors">Visitors today: 1234</p>
</main>
<footer>Rendered at {stamp} &copy; Acme</footer>
</body></html>
"""


class LocalSite:
    """Tiny mutable web site served on a random free port."""

    def __init__(self):
        self.pages = {}
        self.robots = "User-agent: *\nDisallow: /private\n"
        self.requests = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.requests.append((self.command, self.path, self.headers.get("User-Agent")))
                if self.path == "/robots.txt":
                    if site.robots is None:
                        return self._send(404, "text/plain", "not found")
                    if isinstance(site.robots, tuple):
                        return self._send(site.robots[0], "text/plain", site.robots[1])
                    return self._send(200, "text/plain", site.robots)
                path = self.path.split("?")[0]
                if path in site.pages:
                    return self._send(200, "text/html; charset=utf-8", site.pages[path])
                return self._send(404, "text/html", "<html><body><main>nope</main></body></html>")

            def _send(self, status, ctype, body):
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return self.base + path

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site():
    s = LocalSite()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def write_config(tmp_path):
    def _write(pages, name="watch.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"pages": pages}), encoding="utf-8")
        return str(path)
    return _write


@pytest.fixture
def make_page():
    return pricing_page
