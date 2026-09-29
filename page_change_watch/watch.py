"""Core check loop: fetch, extract, normalize, compare with the stored snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Entry
from .diff import html_page, unified_diff, word_changes
from .extract import SelectorError, extract_text
from .fetch import Fetcher, FetchError, RobotsBlocked
from .noise import normalize_lines
from .store import Snapshot, Store, sha256_text, slugify, utc_now

__all__ = ["PageResult", "RunResult", "check_pages"]

NEW, UNCHANGED, CHANGED, ERROR, BLOCKED = "new", "unchanged", "changed", "error", "blocked"


@dataclass
class PageResult:
    name: str
    url: str
    result: str
    checked_at: str
    status: int | None = None
    sha256: str | None = None
    previous_sha256: str | None = None
    previous_at: str | None = None
    lines: int = 0
    error: str | None = None
    diff: list[str] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    html_path: str | None = None
    rendered: bool = False


@dataclass
class RunResult:
    started_at: str
    pages: list[PageResult]
    requests: int = 0

    def count(self, result: str) -> int:
        return sum(1 for p in self.pages if p.result == result)

    @property
    def exit_code(self) -> int:
        if self.count(CHANGED):
            return 1
        if self.count(ERROR) or self.count(BLOCKED):
            return 2
        return 0


def _normalized(lines: list[str], entry: Entry) -> list[str]:
    return normalize_lines(lines, entry.ignore, builtin=entry.default_ignore)


def check_page(entry: Entry, fetcher: Fetcher, store: Store, render: bool = False,
               html_dir: str | Path | None = None) -> PageResult:
    now = utc_now()
    use_render = render or entry.render
    res = PageResult(entry.name, entry.url, ERROR, now, rendered=use_render)
    try:
        resp = fetcher.fetch(entry.url, render=use_render)
        res.status = resp.status
        if not 200 <= resp.status < 300:
            raise FetchError("HTTP %d" % resp.status)
        lines = extract_text(resp.text, entry.selector)
        if not lines:
            raise FetchError("no text extracted (JavaScript page? try render: true)")
        norm = _normalized(lines, entry)
        digest = sha256_text("\n".join(norm))
        res.sha256, res.lines = digest, len(lines)
        prev = store.latest(entry.name)
        snap = Snapshot(entry.name, entry.url, now, resp.status, digest, "\n".join(lines),
                        "\n".join(norm), resp.url, use_render)
        if prev is None:
            res.result = NEW
            store.save(snap)
        else:
            # Re-normalize the previous text with the current rules so that
            # edited ignore patterns never produce a spurious change.
            prev_norm = _normalized(prev.text.split("\n"), entry)
            res.previous_sha256 = sha256_text("\n".join(prev_norm))
            res.previous_at = prev.fetched_at
            if prev_norm == norm:
                res.result = UNCHANGED
            else:
                res.result = CHANGED
                res.diff = unified_diff(prev_norm, norm, "previous " + prev.fetched_at,
                                        "current " + now)
                res.words = word_changes(prev_norm, norm)
                store.save(snap)
                if html_dir:
                    out = Path(html_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    stamp = now.replace(":", "").replace("-", "").split(".")[0] + "Z"
                    path = out / ("%s-%s.html" % (slugify(entry.name), stamp))
                    path.write_text(html_page(entry.name, entry.url, prev_norm, norm,
                                              prev.fetched_at, now, res.previous_sha256, digest),
                                    encoding="utf-8")
                    res.html_path = str(path)
    except RobotsBlocked as exc:
        res.result, res.error = BLOCKED, str(exc)
    except (FetchError, SelectorError, ValueError, OSError) as exc:
        res.result, res.error = ERROR, str(exc)
    store.record_check(entry.name, entry.url, now, res.result, res.status, res.error)
    return res


def check_pages(entries: list[Entry], store: Store, fetcher: Fetcher | None = None,
                render: bool = False, html_dir: str | Path | None = None) -> RunResult:
    own = fetcher is None
    fetcher = fetcher or Fetcher()
    run = RunResult(utc_now(), [])
    try:
        for entry in entries:
            run.pages.append(check_page(entry, fetcher, store, render, html_dir))
    finally:
        if own:
            fetcher.close()
    run.requests = fetcher.requests
    return run
