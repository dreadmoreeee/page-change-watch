"""Line- and word-level diffs (difflib) and the self-contained HTML diff page."""

from __future__ import annotations

import difflib
import html
import re

__all__ = ["unified_diff", "word_changes", "format_word_change", "html_page"]

MAX_WORD_CHANGES = 50
WORD_CONTEXT = 6


def unified_diff(old: list[str], new: list[str], old_label: str = "previous",
                 new_label: str = "current", context: int = 2) -> list[str]:
    return [line.rstrip("\n") for line in
            difflib.unified_diff(old, new, old_label, new_label, n=context, lineterm="")]


def _words(lines: list[str]) -> list[str]:
    words: list[str] = []
    for line in lines:
        words.extend(line.split())
        words.append("\u23ce")  # line break marker, kept out of the rendered text
    return words


def _join(words: list[str]) -> str:
    return " ".join(w for w in words if w != "\u23ce")


def word_changes(old: list[str], new: list[str], limit: int = MAX_WORD_CHANGES) -> list[dict]:
    """Return word-level changes: {op, removed, added, before, after}."""
    a, b = _words(old), _words(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        removed, added = _join(a[i1:i2]), _join(b[j1:j2])
        if not removed and not added:
            continue  # only line breaks moved
        changes.append({
            "op": op,
            "removed": removed,
            "added": added,
            "before": _join(a[max(0, i1 - WORD_CONTEXT):i1]),
            "after": _join(a[i2:i2 + WORD_CONTEXT]),
        })
        if len(changes) >= limit:
            break
    return changes


def format_word_change(ch: dict) -> str:
    """Render one change as ``before [-removed-]{+added+} after``."""
    parts = []
    if ch["before"]:
        parts.append("..." + ch["before"])
    parts.append(("[-%s-]" % ch["removed"] if ch["removed"] else "")
                 + ("{+%s+}" % ch["added"] if ch["added"] else ""))
    if ch["after"]:
        parts.append(ch["after"] + "...")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
margin:0;background:#f6f7f9;color:#1d2330}
.wrap{max-width:960px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}
.meta{color:#5b6475;font-size:13px;margin-bottom:18px}
.meta code{background:#eceef3;padding:1px 4px;border-radius:3px}
table.diff{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dfe3ea;
font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,Menlo,monospace}
table.diff td{padding:2px 8px;vertical-align:top;white-space:pre-wrap;word-break:break-word}
td.n{width:1%;color:#98a1b3;text-align:right;user-select:none;border-right:1px solid #eceef3}
tr.del td.t{background:#fdecee}tr.add td.t{background:#e9f7ee}
tr.skip td{background:#f0f2f6;color:#7a8396;text-align:center}
del{background:#f5b8c0;text-decoration:line-through}ins{background:#a8e2bb;text-decoration:none}
.legend{margin:12px 0;font-size:13px;color:#5b6475}
"""


def _inline(a: str, b: str) -> tuple[str, str]:
    """Word-level highlight for a replaced line pair."""
    wa, wb = re.split(r"(\s+)", a), re.split(r"(\s+)", b)
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    out_a, out_b = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        sa, sb = html.escape("".join(wa[i1:i2])), html.escape("".join(wb[j1:j2]))
        if op == "equal":
            out_a.append(sa)
            out_b.append(sb)
        else:
            if sa:
                out_a.append("<del>%s</del>" % sa)
            if sb:
                out_b.append("<ins>%s</ins>" % sb)
    return "".join(out_a), "".join(out_b)


def _row(cls: str, n_old, n_new, sign: str, body_html: str) -> str:
    return ('<tr class="%s"><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td>'
            '<td class="t">%s</td></tr>' % (cls, n_old or "", n_new or "", sign, body_html))


def html_page(name: str, url: str, old: list[str], new: list[str], old_time: str, new_time: str,
              old_hash: str, new_hash: str, context: int = 3) -> str:
    """Build a self-contained HTML page (no external assets) showing the diff."""
    esc = html.escape
    rows = []
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for group in sm.get_grouped_opcodes(context):
        first = group[0]
        rows.append('<tr class="skip"><td colspan="4">@@ previous line %d, current line %d @@</td></tr>'
                    % (first[1] + 1, first[3] + 1))
        for op, i1, i2, j1, j2 in group:
            if op == "equal":
                for k in range(i2 - i1):
                    rows.append(_row("eq", i1 + k + 1, j1 + k + 1, " ", esc(old[i1 + k])))
                continue
            pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
            dels, adds = [], []
            for k in range(i2 - i1):
                text = esc(old[i1 + k])
                if k < pairs:
                    text = _inline(old[i1 + k], new[j1 + k])[0]
                dels.append(_row("del", i1 + k + 1, None, "-", text))
            for k in range(j2 - j1):
                text = esc(new[j1 + k])
                if k < pairs:
                    text = _inline(old[i1 + k], new[j1 + k])[1]
                adds.append(_row("add", None, j1 + k + 1, "+", text))
            rows.extend(dels)
            rows.extend(adds)
    if not rows:
        rows.append('<tr class="skip"><td colspan="4">No differences.</td></tr>')
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Change: {title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<h1>Change detected: {title}</h1>
<div class="meta"><a href="{href}">{url}</a><br>
Previous: {old_time} <code>{old_hash}</code><br>
Current: {new_time} <code>{new_hash}</code></div>
<div class="legend"><del>removed</del> <ins>added</ins> &middot; noise such as dates and tokens is shown as placeholders</div>
<table class="diff">
{rows}
</table>
</div>
</body>
</html>
""".format(title=esc(name), css=_CSS, href=esc(url, quote=True), url=esc(url),
           old_time=esc(old_time), new_time=esc(new_time), old_hash=esc(old_hash[:16]),
           new_hash=esc(new_hash[:16]), rows="\n".join(rows))
