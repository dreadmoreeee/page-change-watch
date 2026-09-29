"""Markdown and JSON reports."""

from __future__ import annotations

import json
from dataclasses import asdict

from .diff import format_word_change
from .watch import CHANGED, RunResult

__all__ = ["markdown_report", "json_report"]

MAX_DIFF_LINES = 200


def _summary(run: RunResult) -> str:
    return "%d page(s): %d changed, %d unchanged, %d new, %d error(s), %d blocked by robots.txt" % (
        len(run.pages), run.count("changed"), run.count("unchanged"), run.count("new"),
        run.count("error"), run.count("blocked"))


def markdown_report(run: RunResult) -> str:
    out = ["# page-change-watch report", "",
           "Run: %s  " % run.started_at,
           "Result: %s" % _summary(run), "",
           "| Page | Result | HTTP | Lines | SHA-256 | Note |",
           "|---|---|---|---|---|---|"]
    for p in run.pages:
        note = p.error or ("rendered" if p.rendered else "")
        if p.result == "unchanged" and p.previous_at:
            note = (note + "; " if note else "") + "same as " + p.previous_at
        out.append("| [%s](%s) | %s | %s | %s | %s | %s |" % (
            p.name.replace("|", "\\|"), p.url, p.result, p.status if p.status is not None else "-",
            p.lines or "-", "`%s`" % p.sha256[:12] if p.sha256 else "-", note.replace("|", "\\|")))
    for p in run.pages:
        if p.result != CHANGED:
            continue
        out += ["", "## %s: changed" % p.name, "",
                "URL: %s  " % p.url,
                "Previous: %s `%s`  " % (p.previous_at, (p.previous_sha256 or "")[:12]),
                "Current: %s `%s`  " % (p.checked_at, (p.sha256 or "")[:12])]
        if p.html_path:
            out.append("HTML diff: %s" % p.html_path)
        if p.words:
            out += ["", "### Word changes", ""]
            out += ["- `%s`" % format_word_change(w).replace("`", "'") for w in p.words]
        out += ["", "### Unified diff", "", "```diff"]
        out += p.diff[:MAX_DIFF_LINES]
        if len(p.diff) > MAX_DIFF_LINES:
            out.append("... (%d more lines)" % (len(p.diff) - MAX_DIFF_LINES))
        out.append("```")
    return "\n".join(out) + "\n"


def json_report(run: RunResult) -> str:
    data = {
        "tool": "page-change-watch",
        "started_at": run.started_at,
        "exit_code": run.exit_code,
        "summary": {k: run.count(k) for k in ("changed", "unchanged", "new", "error", "blocked")},
        "requests": run.requests,
        "pages": [asdict(p) for p in run.pages],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
