import time

import pytest

from page_change_watch.fetch import Fetcher, FetchError
from page_change_watch.rfc9309 import RobotsTxt

UA = "page-change-watch"


def test_longest_match_wins_not_first():
    r = RobotsTxt("User-agent: *\nDisallow: /\nAllow: /public\n")
    assert r.can_fetch(UA, "https://x.test/public/page")
    assert not r.can_fetch(UA, "https://x.test/other")


def test_allow_wins_tie():
    r = RobotsTxt("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert r.can_fetch(UA, "https://x.test/page")


def test_wildcards_and_end_anchor():
    r = RobotsTxt("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/cache\n")
    assert not r.can_fetch(UA, "https://x.test/a/b.pdf")
    assert r.can_fetch(UA, "https://x.test/a/b.pdf?x=1")
    assert not r.can_fetch(UA, "https://x.test/tmp123/cache/x")


def test_specific_group_and_merge():
    text = ("User-agent: *\nDisallow: /\n\n"
            "User-agent: Page-Change-Watch\nDisallow: /a\n\n"
            "User-agent: page-change-watch\nDisallow: /b\n")
    r = RobotsTxt(text)
    assert r.can_fetch(UA, "https://x.test/c")
    assert not r.can_fetch(UA, "https://x.test/a")
    assert not r.can_fetch(UA, "https://x.test/b")
    assert not r.can_fetch("otherbot", "https://x.test/c")


def test_multiple_agents_share_group_and_sitemap_does_not_break_group():
    r = RobotsTxt("User-agent: a\nUser-agent: page-change-watch\nSitemap: https://x.test/s.xml\n"
                        "Disallow: /x\n")
    assert not r.can_fetch(UA, "https://x.test/x")
    assert r.sitemaps == ["https://x.test/s.xml"]


def test_percent_encoding_and_robots_txt_always_allowed():
    r = RobotsTxt("User-agent: *\nDisallow: /caf\u00e9\nDisallow: /\n")
    assert not r.can_fetch(UA, "https://x.test/caf%C3%A9")
    assert r.can_fetch(UA, "https://x.test/robots.txt")


def test_fetcher_status_rules(site):
    site.pages["/a"] = "<main>a</main>"
    fetcher = Fetcher(delay=0, timeout=5)
    site.robots = None  # 404: everything allowed
    assert fetcher.allowed(site.url("/a"))

    fetcher = Fetcher(delay=0, timeout=5)
    site.robots = (503, "busy")  # 5xx: everything disallowed, reported as an error
    with pytest.raises(FetchError, match="HTTP 503"):
        fetcher.allowed(site.url("/a"))

    fetcher = Fetcher(delay=0, timeout=1)
    port = site.port
    site.close()  # unreachable: disallowed
    with pytest.raises(FetchError, match="unreachable"):
        fetcher.allowed("http://127.0.0.1:%d/a" % port)


def test_delay_between_requests(site):
    site.pages["/a"] = "<main>a</main>"
    fetcher = Fetcher(delay=0.3, timeout=5)
    start = time.monotonic()
    fetcher.fetch(site.url("/a"))  # robots.txt + page
    fetcher.fetch(site.url("/a"))  # page (robots.txt cached)
    assert fetcher.requests == 3
    assert time.monotonic() - start >= 0.6


def test_empty_disallow_and_crawl_delay():
    r = RobotsTxt("User-agent: *\nDisallow:\nCrawl-delay: 2\n")
    assert r.can_fetch(UA, "https://x.test/anything")
    assert r.crawl_delay(UA) == 2.0
