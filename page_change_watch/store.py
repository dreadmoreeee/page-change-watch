"""Snapshot store: one folder per page, JSON snapshots, last N kept.

Layout::

    STORE/<slug>/meta.json                      last check (time, status, result)
    STORE/<slug>/snapshots/<UTC timestamp>.json  one per distinct version
    STORE/<slug>/latest.txt                     readable text of the newest snapshot
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["Snapshot", "Store", "slugify", "sha256_text", "utc_now"]

DEFAULT_STORE = ".page-change-watch"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-.")
    return slug or "page"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Snapshot:
    name: str
    url: str
    fetched_at: str
    status: int
    sha256: str
    text: str
    normalized: str
    final_url: str = ""
    rendered: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


class Store:
    def __init__(self, root: str | os.PathLike = DEFAULT_STORE, keep: int = 10):
        self.root = Path(root)
        self.keep = max(1, int(keep))

    def page_dir(self, name: str) -> Path:
        return self.root / slugify(name)

    def _snap_dir(self, name: str) -> Path:
        return self.page_dir(name) / "snapshots"

    def history(self, name: str) -> list[Path]:
        d = self._snap_dir(name)
        if not d.is_dir():
            return []
        return sorted(p for p in d.glob("*.json"))

    def latest(self, name: str) -> Snapshot | None:
        files = self.history(name)
        if not files:
            return None
        return self.load(files[-1])

    @staticmethod
    def load(path: Path) -> Snapshot:
        with open(path, encoding="utf-8") as fh:
            return Snapshot.from_dict(json.load(fh))

    def save(self, snap: Snapshot) -> Path:
        d = self._snap_dir(snap.name)
        d.mkdir(parents=True, exist_ok=True)
        stamp = re.sub(r"[^0-9TZ]", "", snap.fetched_at)
        path = d / (stamp + ".json")
        n = 1
        while path.exists():
            path = d / ("%s-%d.json" % (stamp, n))
            n += 1
        _write_json(path, asdict(snap))
        (self.page_dir(snap.name) / "latest.txt").write_text(snap.text + "\n", encoding="utf-8")
        for old in self.history(snap.name)[:-self.keep]:
            old.unlink()
        return path

    def record_check(self, name: str, url: str, when: str, result: str, status: int | None,
                     error: str | None = None) -> None:
        d = self.page_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        _write_json(d / "meta.json", {"name": name, "url": url, "last_checked": when,
                                      "last_result": result, "last_status": status,
                                      "last_error": error})

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        out = []
        for d in sorted(self.root.iterdir()):
            if (d / "snapshots").is_dir():
                snap = self.latest_in(d)
                out.append(snap.name if snap else d.name)
        return out

    def latest_in(self, page_dir: Path) -> Snapshot | None:
        files = sorted((page_dir / "snapshots").glob("*.json"))
        return self.load(files[-1]) if files else None


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
