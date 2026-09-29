"""Watch-list loading (JSON always; YAML when PyYAML is installed)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .noise import compile_patterns

__all__ = ["ConfigError", "Entry", "load_config", "parse_config"]


class ConfigError(Exception):
    pass


@dataclass
class Entry:
    name: str
    url: str
    selector: str | None = None
    ignore: list[str] = field(default_factory=list)
    render: bool = False
    default_ignore: bool = True


def _name_from_url(url: str) -> str:
    parts = urlsplit(url)
    return (parts.netloc + parts.path).rstrip("/") or url


def parse_config(data) -> list[Entry]:
    """Accept ``{"pages": [...], "defaults": {...}}`` or a bare list of entries."""
    defaults: dict = {}
    if isinstance(data, dict):
        defaults = data.get("defaults") or {}
        pages = data.get("pages", data.get("watch"))
    else:
        pages = data
    if not isinstance(pages, list) or not pages:
        raise ConfigError("config must contain a non-empty 'pages' list")
    if not isinstance(defaults, dict):
        raise ConfigError("'defaults' must be a mapping")
    entries, seen = [], set()
    for i, raw in enumerate(pages, 1):
        if isinstance(raw, str):
            raw = {"url": raw}
        if not isinstance(raw, dict):
            raise ConfigError("entry %d must be a mapping or a URL string" % i)
        url = raw.get("url")
        if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
            raise ConfigError("entry %d: 'url' must be an http(s) URL" % i)
        name = str(raw.get("name") or raw.get("id") or _name_from_url(url))
        if name in seen:
            raise ConfigError("duplicate entry name %r" % name)
        seen.add(name)
        ignore = list(defaults.get("ignore") or []) + list(raw.get("ignore") or [])
        if isinstance(raw.get("ignore"), str):
            ignore = list(defaults.get("ignore") or []) + [raw["ignore"]]
        try:
            compile_patterns(ignore)
        except ValueError as exc:
            raise ConfigError("entry %r: %s" % (name, exc)) from None
        entries.append(Entry(
            name=name,
            url=url,
            selector=raw.get("selector", defaults.get("selector")) or None,
            ignore=ignore,
            render=bool(raw.get("render", defaults.get("render", False))),
            default_ignore=bool(raw.get("default_ignore", defaults.get("default_ignore", True))),
        ))
    return entries


def load_config(path: str | Path) -> list[Entry]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc.strerror or exc)) from None
    if path.suffix.lower() in (".yml", ".yaml"):
        try:
            import yaml
        except ImportError:
            raise ConfigError("YAML config needs PyYAML (pip install pyyaml); "
                              "or use a .json watch list") from None
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError("invalid YAML in %s: %s" % (path, exc)) from None
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError("invalid JSON in %s: %s" % (path, exc)) from None
    return parse_config(data)
