"""Command line interface: ``page-change-watch run|show|list``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_config
from .fetch import Fetcher
from .report import json_report, markdown_report
from .store import DEFAULT_STORE, Store
from .watch import check_pages

EXIT_OK, EXIT_CHANGED, EXIT_ERROR = 0, 1, 2


def _non_negative(value: str) -> float:
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("not a number: %r" % value) from None
    if f < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return f


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="page-change-watch",
                                description="Watch web pages for meaningful content changes.")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="check every page in a watch list")
    run.add_argument("-c", "--config", required=True, help="watch list (.json, .yml, .yaml)")
    run.add_argument("--store", default=DEFAULT_STORE, help="snapshot folder (default: %(default)s)")
    run.add_argument("--render", action="store_true", help="render every page with headless Chromium")
    run.add_argument("--format", choices=("markdown", "json"), default="markdown")
    run.add_argument("--output", "-o", help="write the report to this file instead of stdout")
    run.add_argument("--html", metavar="DIR", help="write a self-contained HTML diff page per change")
    run.add_argument("--keep", type=int, default=10, help="snapshots kept per page (default: 10)")
    run.add_argument("--delay", type=_non_negative, default=1.0,
                     help="seconds between requests (default: 1.0)")
    run.add_argument("--timeout", type=_non_negative, default=20.0,
                     help="request timeout in seconds (default: 20)")

    show = sub.add_parser("show", help="print the latest snapshot text of a page")
    show.add_argument("name")
    show.add_argument("--store", default=DEFAULT_STORE)
    show.add_argument("--normalized", action="store_true",
                      help="print the noise-filtered text that is hashed")

    lst = sub.add_parser("list", help="list pages in the snapshot store")
    lst.add_argument("--store", default=DEFAULT_STORE)
    return p


def _cmd_run(args) -> int:
    try:
        entries = load_config(args.config)
    except ConfigError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    store = Store(args.store, keep=args.keep)
    fetcher = Fetcher(delay=args.delay, timeout=args.timeout)
    try:
        run = check_pages(entries, store, fetcher, render=args.render, html_dir=args.html)
    finally:
        fetcher.close()
    report = json_report(run) if args.format == "json" else markdown_report(run)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return run.exit_code


def _cmd_show(args) -> int:
    store = Store(args.store)
    snap = store.latest(args.name)
    if snap is None:
        print("error: no snapshot for %r in %s" % (args.name, args.store), file=sys.stderr)
        return EXIT_ERROR
    print("# %s  %s  %s  sha256:%s" % (snap.name, snap.url, snap.fetched_at, snap.sha256[:12]))
    print(snap.normalized if args.normalized else snap.text)
    return EXIT_OK


def _cmd_list(args) -> int:
    store = Store(args.store)
    for name in store.names():
        snap = store.latest(name)
        count = len(store.history(name))
        print("%s\t%s\t%s\t%d snapshot(s)" % (name, snap.url if snap else "",
                                             snap.fetched_at if snap else "", count))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "show":
            return _cmd_show(args)
        return _cmd_list(args)
    except KeyboardInterrupt:
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
