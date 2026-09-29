import pytest

from page_change_watch.cli import main

JS_PAGE = """<!DOCTYPE html><html><body><main><h1>Menu</h1><div id="price">loading</div></main>
<script>document.getElementById('price').textContent = 'Burger ' + '$' + (%d + 1);</script>
</body></html>"""


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "playwright not installed"
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
    except Exception as exc:  # browser binaries missing, sandbox issues...
        return "chromium unavailable: %s" % str(exc).splitlines()[0]
    return None


def test_render_mode_sees_javascript_content(site, write_config, tmp_path, capsys):
    reason = _chromium_available()
    if reason:
        pytest.skip(reason)
    site.pages["/menu"] = JS_PAGE % 13
    cfg = write_config([{"name": "menu", "url": site.url("/menu"), "render": True}])
    store = tmp_path / "s"
    args = ["run", "-c", cfg, "--store", str(store), "--delay", "0", "--timeout", "30"]
    assert main(args) == 0
    capsys.readouterr()
    main(["show", "menu", "--store", str(store)])
    shown = capsys.readouterr().out
    assert "Burger $14" in shown and "loading" not in shown

    site.pages["/menu"] = JS_PAGE % 15
    assert main(args) == 1
    assert "[-$14-]{+$16+}" in capsys.readouterr().out


def test_plain_mode_does_not_need_playwright(site, write_config, tmp_path, capsys):
    site.pages["/menu"] = JS_PAGE % 13
    cfg = write_config([{"name": "menu", "url": site.url("/menu")}])
    assert main(["run", "-c", cfg, "--store", str(tmp_path / "s"), "--delay", "0"]) == 0
    main(["show", "menu", "--store", str(tmp_path / "s")])
    assert "loading" in capsys.readouterr().out
