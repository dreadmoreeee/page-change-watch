import pytest

from page_change_watch.extract import SelectorError, extract_text, parse_html, select

DOC = """<html><head><title>T</title><style>p{}</style></head><body>
<header id="top"><h1>Site</h1></header>
<nav>Menu</nav>
<div id="app" class="wrap outer">
  <article class="post"><header><h2>Post title</h2></header><p>Body <b>bold</b> text.</p>
    <footer>by Ann</footer></article>
  <ul class="list"><li>One<li>Two <span class="tag hot">hot</span></ul>
  <table><tr><td>Plan</td><td>$5</td></tr><tr><td>Pro<td>$9</table>
  <p data-kind="note">Note</p>
  <div hidden>secret</div><div style="display: none">gone</div>
  <svg><text>svgtext</text></svg><noscript>enable js</noscript>
  <template><p>tpl</p></template>
</div>
<footer>Copyright</footer>
<script>var a = "<p>no</p>";</script>
</body></html>"""


def tags(nodes):
    return [n.tag for n in nodes]


def test_selectors():
    root = parse_html(DOC)
    assert tags(select(root, "article")) == ["article"]
    assert tags(select(root, "#app")) == ["div"]
    assert tags(select(root, ".tag")) == ["span"]
    assert tags(select(root, "span.tag.hot")) == ["span"]
    assert tags(select(root, "div.wrap .list li")) == ["li", "li"]
    assert tags(select(root, "ul > li")) == ["li", "li"]
    assert tags(select(root, "body > li")) == []
    assert tags(select(root, "[data-kind=note]")) == ["p"]
    assert tags(select(root, "p[data-kind^=no]")) == ["p"]
    assert tags(select(root, "h2, ul")) == ["h2", "ul"]
    # outermost only
    assert tags(select(root, "div, article")) == ["div"]


def test_bad_selector():
    with pytest.raises(SelectorError):
        select(parse_html(DOC), "a:hover")
    with pytest.raises(SelectorError):
        select(parse_html(DOC), "> p")


def test_article_is_preferred_and_chrome_stripped():
    lines = extract_text(DOC)
    assert lines == ["Post title", "Body bold text.", "by Ann"]


def test_body_fallback_strips_noise():
    doc = DOC.replace("<article", "<section").replace("</article>", "</section>")
    lines = extract_text(doc)
    text = "\n".join(lines)
    assert "Post title" in text and "One" in text and "Two hot" in text
    assert "Plan $5" in text and "Pro $9" in text
    for noise in ("Site", "Menu", "Copyright", "secret", "gone", "svgtext", "enable js", "tpl", "no"):
        assert noise not in lines
    assert "var a" not in text


def test_main_wins_over_article():
    html = "<body><article>A</article><main><p>M</p></main></body>"
    assert extract_text(html) == ["M"]
    assert extract_text('<body><div role="main">R</div><p>x</p></body>') == ["R"]


def test_selector_extract():
    assert extract_text(DOC, "td") == ["Plan", "$5", "Pro", "$9"]
    with pytest.raises(SelectorError):
        extract_text(DOC, ".nothing")
    # an explicitly selected chrome element is kept
    assert extract_text(DOC, "nav") == ["Menu"]


def test_entities_and_whitespace():
    html = "<main><p>A&nbsp;&amp;\n\n   B</p><p>caf&eacute;</p><br><p>  </p></main>"
    assert extract_text(html) == ["A & B", "caf\u00e9"]


def test_unclosed_head_does_not_hide_body():
    assert extract_text("<html><head><title>x</title><body><p>Hello</p>") == ["Hello"]
