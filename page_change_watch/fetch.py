"""Polite HTTP fetching (stdlib urllib) with robots.txt and optional Playwright rendering."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .rfc9309 import MAX_BYTES, RobotsTxt

__all__ = ["USER_AGENT", "ROBOTS_TOKEN", "FetchError", "Response", "Fetcher"]

USER_AGENT = "page-change-watch/1.0 (+https://github.com/dreadmoreeee/page-change-watch)"
ROBOTS_TOKEN = "page-change-watch"
DISALLOW_ALL = "User-agent: *\nDisallow: /\n"


class FetchError(Exception):
    pass


class RobotsBlocked(FetchError):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str
    content_type: str = ""


_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""", re.I)


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    charset = m.group(1) if m else None
    if not charset:
        mm = _META_CHARSET.search(body[:4096])
        charset = mm.group(1).decode("ascii") if mm else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FetchError("only http(s) URLs are supported: %r" % url)


class Fetcher:
    """GET-only fetcher with a global minimum interval between requests."""

    def __init__(self, delay: float = 1.0, timeout: float = 20.0, user_agent: str = USER_AGENT,
                 max_bytes: int = 5_000_000, respect_robots: bool = True):
        self.delay = max(0.0, float(delay))
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.respect_robots = respect_robots
        self.requests = 0
        self._last = None
        self._robots: dict[str, RobotsTxt] = {}
        self._robots_errors: dict[str, str] = {}
        self._renderer = None

    # -- politeness -----------------------------------------------------------
    def wait(self) -> None:
        if self._last is not None and self.delay:
            # loop: time.sleep may wake a few ms early on coarse clocks (Windows)
            while (remaining := self.delay - (time.monotonic() - self._last)) > 0:
                time.sleep(remaining + 0.005)
        self._last = time.monotonic()
        self.requests += 1

    # -- raw GET --------------------------------------------------------------
    def _get(self, url: str, limit: int) -> tuple[int, str, bytes, str]:
        self.wait()
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en;q=0.9,*;q=0.5",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.geturl(), resp.read(limit), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(limit)
            except Exception:
                pass
            return exc.code, exc.geturl() or url, body, exc.headers.get("Content-Type", "") if exc.headers else ""

    # -- robots.txt -----------------------------------------------------------
    def robots_for(self, url: str) -> RobotsTxt:
        parts = urlsplit(url)
        origin = "%s://%s" % (parts.scheme, parts.netloc)
        if origin not in self._robots:
            robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
            # RFC 9309 2.3.1: 2xx parse, 4xx allow all, 5xx/unreachable disallow all.
            try:
                status, _final, body, _ct = self._get(robots_url, MAX_BYTES)
                if 200 <= status < 300:
                    robots = RobotsTxt(body.decode("utf-8", errors="replace"))
                elif status < 500:
                    robots = RobotsTxt("")
                else:
                    robots = RobotsTxt(DISALLOW_ALL)
                    self._robots_errors[origin] = "robots.txt returned HTTP %d" % status
            except (urllib.error.URLError, OSError, ValueError) as exc:
                robots = RobotsTxt(DISALLOW_ALL)
                self._robots_errors[origin] = "robots.txt unreachable: %s" % getattr(exc, "reason", exc)
            self._robots[origin] = robots
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        robots = self.robots_for(url)
        parts = urlsplit(url)
        error = self._robots_errors.get("%s://%s" % (parts.scheme, parts.netloc))
        if error:
            raise FetchError(error + " (treated as disallow-all)")
        return robots.can_fetch(ROBOTS_TOKEN, url)

    # -- public ---------------------------------------------------------------
    def fetch(self, url: str, render: bool = False) -> Response:
        _check_url(url)
        if not self.allowed(url):
            raise RobotsBlocked("disallowed by robots.txt: %s" % url)
        if render:
            return self._render(url)
        try:
            status, final, body, ctype = self._get(url, self.max_bytes)
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise FetchError("request failed: %s" % reason) from None
        return Response(final, status, _decode(body, ctype), ctype)

    def _render(self, url: str) -> Response:
        if self._renderer is None:
            self._renderer = Renderer(self.timeout, self.user_agent)
        self.wait()
        return self._renderer.get(url)

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


class Renderer:
    """Headless Chromium via Playwright; imported lazily."""

    def __init__(self, timeout: float, user_agent: str):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise FetchError("render mode needs Playwright: pip install playwright && "
                             "playwright install chromium") from None
        self.timeout_ms = int(timeout * 1000)
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:
            self._pw.stop()
            raise FetchError("could not launch Chromium: %s" % str(exc).splitlines()[0]) from None
        self._context = self._browser.new_context(user_agent=user_agent)

    def get(self, url: str) -> Response:
        page = self._context.new_page()
        try:
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            except Exception:
                resp = page.goto(url, wait_until="load", timeout=self.timeout_ms)
            status = resp.status if resp is not None else 200
            return Response(page.url, status, page.content(), "text/html")
        except Exception as exc:
            raise FetchError("render failed: %s" % str(exc).splitlines()[0]) from None
        finally:
            page.close()

    def close(self) -> None:
        try:
            self._context.close()
            self._browser.close()
        finally:
            self._pw.stop()
