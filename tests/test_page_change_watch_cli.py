import json
import subprocess
import sys
from pathlib import Path

from page_change_watch.cli import main
from page_change_watch.fetch import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]


def run(config, store, *extra):
    return main(["run", "-c", config, "--store", str(store), "--delay", "0", "--timeout", "5", *extra])


def test_baseline_then_noise_only_is_unchanged(site, write_config, make_page, tmp_path, capsys):
    site.pages["/pricing"] = make_page()
    cfg = write_config([{"name": "pricing", "url": site.url("/pricing")}])
    store = tmp_path / "store"

    assert run(cfg, store) == 0
    out = capsys.readouterr().out
    assert "| new |" in out and "0 changed" in out

    site.pages["/pricing"] = make_page(
        stamp="2026-10-01 18:42:07", token="Qw8ErT5yUi3OpA1sDf7GhJ2k", nav="Home (new menu)",
        script="var build = 2; track('x');", cb="v=2002", ago="3 hours ago",
        long_date="Oct 1, 2026 at 6:42 PM", hexhash="2c26b46b68ffc68ff99b453c1d304134")
    assert run(cfg, store) == 0
    out = capsys.readouterr().out
    assert "| unchanged |" in out and "0 changed" in out

    # every request identified itself and used GET
    assert all(m == "GET" and ua == USER_AGENT for m, _p, ua in site.requests)
    assert ("GET", "/robots.txt", USER_AGENT) in site.requests


def test_real_change_is_detected(site, write_config, make_page, tmp_path, capsys):
    site.pages["/pricing"] = make_page(price="$19")
    cfg = write_config([{"name": "pricing", "url": site.url("/pricing")}])
    store = tmp_path / "store"
    assert run(cfg, store) == 0
    capsys.readouterr()

    site.pages["/pricing"] = make_page(price="$24", stamp="2026-10-02 08:00:00")
    assert run(cfg, store) == 1
    out = capsys.readouterr().out
    assert "## pricing: changed" in out
    assert "-Pro $19 per month" in out and "+Pro $24 per month" in out
    assert "[-$19-]{+$24+}" in out
    # history keeps both versions; show prints the latest text
    assert main(["show", "pricing", "--store", str(store)]) == 0
    shown = capsys.readouterr().out
    assert "Pro $24 per month" in shown and "Rendered at" not in shown and "Blog" not in shown

    # third run without changes: back to exit 0
    assert run(cfg, store) == 0


def test_json_report(site, write_config, make_page, tmp_path, capsys):
    site.pages["/p"] = make_page()
    cfg = write_config([{"name": "p", "url": site.url("/p")}])
    store = tmp_path / "s"
    run(cfg, store)
    capsys.readouterr()
    site.pages["/p"] = make_page(price="$29")
    out_file = tmp_path / "report.json"
    assert run(cfg, store, "--format", "json", "--output", str(out_file)) == 1
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["summary"]["changed"] == 1 and data["exit_code"] == 1
    page = data["pages"][0]
    assert page["result"] == "changed"
    assert any(w["removed"].endswith("$19") or w["removed"] == "$19" for w in page["words"])
    assert any("+Pro $29 per month" in line for line in page["diff"])


def test_selector_scoping(site, write_config, make_page, tmp_path, capsys):
    site.pages["/pricing"] = make_page()
    cfg = write_config([{"name": "pro", "url": site.url("/pricing"), "selector": ".plan .price"}])
    store = tmp_path / "store"
    assert run(cfg, store) == 0
    capsys.readouterr()
    main(["show", "pro", "--store", str(store)])
    shown = capsys.readouterr().out.splitlines()[1:]
    assert shown == ["$19", "$49"]
    # a change outside the selected elements is ignored
    site.pages["/pricing"] = make_page().replace("<h1>Pricing</h1>", "<h1>Plans and pricing</h1>")
    assert run(cfg, store) == 0
    capsys.readouterr()
    site.pages["/pricing"] = make_page(price="$21")
    assert run(cfg, store) == 1


def test_selector_matching_nothing_is_an_error(site, write_config, make_page, tmp_path, capsys):
    site.pages["/pricing"] = make_page()
    cfg = write_config([{"name": "x", "url": site.url("/pricing"), "selector": "#missing"}])
    assert run(cfg, tmp_path / "s") == 2
    assert "matched nothing" in capsys.readouterr().out


def test_custom_ignore_regex(site, write_config, make_page, tmp_path, capsys):
    site.pages["/pricing"] = make_page()
    cfg = write_config([{"name": "p", "url": site.url("/pricing"), "ignore": [r"Visitors today: \d+"]}])
    store = tmp_path / "store"
    assert run(cfg, store) == 0
    site.pages["/pricing"] = make_page().replace("Visitors today: 1234", "Visitors today: 98765")
    assert run(cfg, store) == 0
    # without the custom pattern the counter is a real change
    cfg2 = write_config([{"name": "p", "url": site.url("/pricing")}], name="plain.json")
    store2 = tmp_path / "store2"
    site.pages["/pricing"] = make_page()
    assert run(cfg2, store2) == 0
    site.pages["/pricing"] = make_page().replace("Visitors today: 1234", "Visitors today: 98765")
    assert run(cfg2, store2) == 1
    capsys.readouterr()


def test_robots_disallow_is_honored(site, write_config, make_page, tmp_path, capsys):
    site.robots = "User-agent: *\nDisallow: /private\nAllow: /private/ok\n"
    site.pages["/private/secret"] = make_page()
    site.pages["/private/ok"] = make_page()
    cfg = write_config([{"name": "secret", "url": site.url("/private/secret")},
                        {"name": "ok", "url": site.url("/private/ok")}])
    assert run(cfg, tmp_path / "s") == 2
    out = capsys.readouterr().out
    assert "| blocked |" in out and "disallowed by robots.txt" in out
    paths = [p for _m, p, _ua in site.requests]
    assert "/private/secret" not in paths
    assert "/private/ok" in paths
    assert paths.count("/robots.txt") == 1  # cached per origin


def test_robots_missing_means_allowed(site, write_config, make_page, tmp_path, capsys):
    site.robots = None  # 404
    site.pages["/private/x"] = make_page()
    cfg = write_config([{"name": "x", "url": site.url("/private/x")}])
    assert run(cfg, tmp_path / "s") == 0


def test_http_error_exit_2(site, write_config, tmp_path, capsys):
    cfg = write_config([{"name": "gone", "url": site.url("/does-not-exist")}])
    assert run(cfg, tmp_path / "s") == 2
    assert "HTTP 404" in capsys.readouterr().out


def test_html_diff_page_is_escaped(site, write_config, make_page, tmp_path, capsys):
    site.pages["/p"] = make_page(price="$19")
    cfg = write_config([{"name": "p<x>", "url": site.url("/p")}])
    store, html_dir = tmp_path / "store", tmp_path / "html"
    run(cfg, store, "--html", str(html_dir))
    assert not html_dir.exists() or not list(html_dir.iterdir())  # baseline: no diff page
    site.pages["/p"] = make_page(price="&lt;script&gt;alert(1)&lt;/script&gt; $25")
    assert run(cfg, store, "--html", str(html_dir)) == 1
    files = list(html_dir.glob("*.html"))
    assert len(files) == 1
    page = files[0].read_text(encoding="utf-8")
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<ins>" in page and "<del>" in page and "$19" in page
    assert "Change detected: p&lt;x&gt;" in page
    assert "http://" not in page.split("<body>")[0] and "https://" not in page.split("<body>")[0]
    assert "HTML diff:" in capsys.readouterr().out


def test_yaml_config_and_defaults(site, make_page, tmp_path, capsys):
    site.pages["/p"] = make_page()
    cfg = tmp_path / "watch.yml"
    cfg.write_text(
        "defaults:\n  ignore:\n    - 'Visitors today: \\d+'\n"
        "pages:\n  - id: pricing\n    url: %s\n    selector: main\n" % site.url("/p"),
        encoding="utf-8")
    store = tmp_path / "s"
    assert run(str(cfg), store) == 0
    site.pages["/p"] = make_page().replace("1234", "4321")
    assert run(str(cfg), store) == 0
    capsys.readouterr()
    assert main(["list", "--store", str(store)]) == 0
    assert "pricing" in capsys.readouterr().out


def test_usage_errors_exit_2(tmp_path, capsys):
    assert main(["run", "-c", str(tmp_path / "missing.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text('{"pages": [{"url": "ftp://x"}]}', encoding="utf-8")
    assert main(["run", "-c", str(bad)]) == 2
    assert main(["show", "nothing", "--store", str(tmp_path)]) == 2
    try:
        main(["bogus"])
    except SystemExit as exc:
        assert exc.code == 2


def test_python_dash_m(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "page_change_watch", "--version"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0 and "page-change-watch" in proc.stdout


def test_example_watch_lists_parse():
    from page_change_watch.config import load_config
    yml = load_config(ROOT / "examples" / "watch.yml")
    js = load_config(ROOT / "examples" / "watch.json")
    assert yml == js
    assert [e.name for e in js] == ["competitor-pricing", "terms", "my-home-after-deploy", "opening-hours"]
    assert js[2].render and not js[3].default_ignore
    assert len(load_config(ROOT / "examples" / "demark-watch.yml")) == 3


def test_history_is_trimmed(site, write_config, make_page, tmp_path, capsys):
    cfg = write_config([{"name": "p", "url": site.url("/p")}])
    store = tmp_path / "s"
    for i in range(5):
        site.pages["/p"] = make_page(price="$%d" % (10 + i))
        run(cfg, store, "--keep", "3")
    snaps = list((store / "p" / "snapshots").glob("*.json"))
    assert len(snaps) == 3
    capsys.readouterr()
