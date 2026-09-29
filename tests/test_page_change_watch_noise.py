import pytest

from page_change_watch.noise import normalize_lines


def norm(text, **kw):
    return normalize_lines([text], **kw)[0] if normalize_lines([text], **kw) else ""


@pytest.mark.parametrize("text", [
    "Updated 2026-09-29",
    "Updated 2026-09-29T10:11:12Z",
    "Updated 2026-09-29 10:11:12+02:00",
    "Updated 09/29/2026",
    "Updated 29.09.2026",
    "Updated 2026/09/29",
    "Updated September 29, 2026",
    "Updated Sep 29",
    "Updated Tuesday, 29 September 2026",
    "Updated 29th of September 2026",
])
def test_dates(text):
    assert norm(text) == "Updated [date]"


@pytest.mark.parametrize("text,expected", [
    ("at 10:11", "at [time]"),
    ("at 10:11:12", "at [time]"),
    ("at 6:42 PM", "at [time]"),
    ("at 6:42pm EST", "at [time]"),
    ("posted 5 minutes ago", "posted [ago]"),
    ("posted an hour ago", "posted [ago]"),
    ("posted 3 days ago", "posted [ago]"),
    ("posted just now", "posted [ago]"),
])
def test_times(text, expected):
    assert norm(text) == expected


def test_tokens_and_hashes():
    assert norm("csrf_token=abcDEF123456") == "csrf_token=[token]"
    assert norm('nonce: "k8Js0Pq7"') == 'nonce: "[token]"'
    assert norm("build 9f86d081884c7d659a2feaa0c55ad015") == "build [hash]"
    assert norm("id 123e4567-e89b-12d3-a456-426614174000") == "id [id]"
    assert norm("x a8F3kLq9Zx2Wv7Pt5RmN0bYc y") == "x [token] y"
    assert norm("see /app.js?v=12345 and style.css?ver=abc&x=1") == \
        "see /app.js?v=[cache] and style.css?ver=[cache]&x=1"
    assert norm("bundle.js?1695912345") == "bundle.js?[cache]"


def test_meaningful_content_is_kept():
    for text in ("Pro $19.99 per month", "Call 506-555-0123", "Version 2.4.1", "Only 3 left",
                 "Open 7 days a week", "extraordinarilylongwordwithoutdigits",
                 "/products/some-long-product-slug-2026"):
        assert norm(text) == text


def test_user_patterns_remove_and_drop_empty_lines():
    lines = ["Visitors: 42", "Price $5 (ref 991)"]
    out = normalize_lines(lines, ignore=[r"^Visitors: \d+$", r"\(ref \d+\)"])
    assert out == ["Price $5"]


def test_builtin_can_be_disabled():
    assert normalize_lines(["Open 10:00"], builtin=False) == ["Open 10:00"]


def test_invalid_regex():
    with pytest.raises(ValueError):
        normalize_lines(["x"], ignore=["("])
