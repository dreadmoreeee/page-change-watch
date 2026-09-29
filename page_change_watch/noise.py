"""Noise filtering: turn volatile fragments into stable placeholders.

Built-in filters replace matches with a placeholder such as ``[date]`` so that
only meaningful edits change the page hash. User patterns (regexes) are removed
entirely; a line that becomes empty is dropped.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

__all__ = ["BUILTIN_FILTERS", "compile_patterns", "normalize_lines"]

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
          r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_WEEKDAY = (r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:rs(?:day)?)?|Fri(?:day)?|"
            r"Sat(?:urday)?|Sun(?:day)?)\.?,?\s+")
_CACHE_KEYS = r"(?:v|ver|version|cb|cachebust|cache|cachebuster|nocache|_|t|ts|timestamp|rev|build|hash|h)"


def _random_token(m: re.Match) -> str:
    s = m.group(0)
    core = s.rstrip("=")
    if (any(c.isdigit() for c in core) and any(c.isupper() for c in core)
            and any(c.islower() for c in core)):
        return "[token]"
    return s


# (name, compiled regex, replacement)
BUILTIN_FILTERS: list[tuple[str, re.Pattern, str | Callable]] = [
    ("cache-busting query", re.compile(r"([?&]" + _CACHE_KEYS + r"=)[^&#\s\"'<>)]*", re.I),
     r"\1[cache]"),
    ("cache-busting query", re.compile(r"\?\d{6,}\b"), "?[cache]"),
    ("iso datetime", re.compile(
        r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?"
        r"(?:\s?(?:Z|UTC|GMT|[+-]\d{2}:?\d{2}))?)?(?![\w-])"), "[date]"),
    ("numeric date", re.compile(r"\b\d{4}([/.])\d{1,2}\1\d{1,2}\b"), "[date]"),
    ("numeric date", re.compile(r"\b\d{1,2}([/.-])\d{1,2}\1(?:\d{4}|\d{2})\b"), "[date]"),
    ("month date", re.compile(
        r"\b(?:" + _WEEKDAY + r")?" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b", re.I),
     "[date]"),
    ("month date", re.compile(
        r"\b(?:" + _WEEKDAY + r")?\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH + r",?\s+\d{4}\b", re.I),
     "[date]"),
    ("time", re.compile(
        r"\b\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s?[AaPp]\.?[Mm]\b\.?)?"
        r"(?:\s?(?:UTC|GMT|[ECMP][SD]T|[AE][SD]T|Z)\b)?"), "[time]"),
    ("relative time", re.compile(
        r"\b(?:\d+|an?|one|a few|several)\s+(?:sec(?:ond)?s?|min(?:ute)?s?|h(?:ou)?rs?|hours?|"
        r"days?|weeks?|wks?|months?|mos?|years?|yrs?)\s+ago\b", re.I), "[ago]"),
    ("relative time", re.compile(r"\bjust now\b", re.I), "[ago]"),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
     "[id]"),
    ("csrf/nonce token", re.compile(
        r"(\b(?:csrf|xsrf|nonce|token|authenticity_token|requestverificationtoken|"
        r"csrfmiddlewaretoken)[\w-]*[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9+/_.=-]{6,}", re.I),
     r"\1[token]"),
    ("hex hash", re.compile(r"\b[0-9a-fA-F]{16,}\b"), "[hash]"),
    ("base64 token", re.compile(r"(?<![\w+/=-])[A-Za-z0-9+/_-]{20,}={0,2}(?![\w+/=-])"), _random_token),
]

_WS = re.compile(r"\s+")


def compile_patterns(patterns: Iterable[str]) -> list[re.Pattern]:
    compiled = []
    for pat in patterns or []:
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            raise ValueError("invalid ignore regex %r: %s" % (pat, exc)) from None
    return compiled


def normalize_line(line: str, user: list[re.Pattern], builtin: bool = True) -> str:
    for pat in user:
        line = pat.sub("", line)
    if builtin:
        for _name, pat, repl in BUILTIN_FILTERS:
            line = pat.sub(repl, line)
    return _WS.sub(" ", line).strip()


def normalize_lines(lines: Iterable[str], ignore: Iterable[str] = (), builtin: bool = True) -> list[str]:
    """Apply user ``ignore`` regexes (removed) and built-in filters (placeholders)."""
    user = compile_patterns(ignore)
    out = []
    for line in lines:
        line = normalize_line(line, user, builtin)
        if line:
            out.append(line)
    return out
