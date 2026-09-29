"""HTML -> main-content text, using only the stdlib html.parser.

Supported CSS selector subset (see README):
  tag, *, #id, .class, [attr], [attr=value], [attr~=value], [attr^=value],
  [attr$=value], [attr*=value], compounds such as ``div.price#main``,
  descendant (``main .price``) and child (``ul > li``) combinators, and
  comma-separated groups.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

__all__ = ["Node", "parse_html", "select", "extract_text", "SelectorError"]

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "keygen"}
# Subtrees dropped while parsing: never visible page text.
DROP = {"script", "style", "noscript", "template", "svg", "math", "iframe", "object",
        "canvas", "title"}
# Subtrees skipped when extracting text (page chrome).
CHROME = {"nav", "aside"}
CHROME_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search"}
SECTIONING = {"article", "aside", "main", "nav", "section", "body"}
BLOCK = {"address", "article", "aside", "blockquote", "body", "br", "caption", "dd", "details",
         "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
         "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "html", "legend", "li", "main",
         "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "tfoot", "thead",
         "tr", "ul", "option", "label", "button"}
CELL = {"td", "th"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def iter(self):
        """Yield this node and all element descendants in document order."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed([c for c in node.children if isinstance(c, Node)]))

    def find_all(self, tag: str) -> list["Node"]:
        return [n for n in self.iter() if n.tag == tag]

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Node %s %r>" % (self.tag, self.attrs)


# Implicitly closed elements: starting KEY closes an open element in VALUE,
# as long as no element from the barrier set sits in between.
_IMPLIED = {
    "li": ({"li"}, {"ul", "ol", "menu"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
    "tr": ({"tr", "td", "th"}, {"table", "tbody", "thead", "tfoot"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "option": ({"option"}, {"select", "datalist", "optgroup"}),
    "tbody": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}),
    "thead": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}),
    "tfoot": ({"tbody", "thead", "tfoot", "tr", "td", "th"}, {"table"}),
}
_CLOSES_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset",
             "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
             "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul"}


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.stack = [self.root]
        self.skip_tag: str | None = None
        self.skip_depth = 0

    @property
    def top(self) -> Node:
        return self.stack[-1]

    def _close_to(self, index: int) -> None:
        del self.stack[index:]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_tag:
            if tag == self.skip_tag and tag not in VOID:
                self.skip_depth += 1
            return
        if tag in DROP:
            self.skip_tag, self.skip_depth = tag, 1
            return
        if tag in _CLOSES_P and self.top.tag == "p":
            self.stack.pop()
        rule = _IMPLIED.get(tag)
        if rule:
            closes, barrier = rule
            for i in range(len(self.stack) - 1, 0, -1):
                t = self.stack[i].tag
                if t in closes:
                    self._close_to(i)
                    break
                if t in barrier:
                    break
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.top)
        self.top.children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_tag:
            return
        if tag in DROP:
            return
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.top)
        self.top.children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth <= 0:
                    self.skip_tag, self.skip_depth = None, 0
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self._close_to(i)
                return

    def handle_data(self, data):
        if self.skip_tag or not data:
            return
        self.top.children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

class SelectorError(ValueError):
    pass


_TOKEN = re.compile(r"""
    (?P<ws>\s*>\s*|\s+)
  | (?P<tag>\*|[A-Za-z][\w-]*)
  | \#(?P<id>[\w-]+)
  | \.(?P<cls>[\w-]+)
  | \[\s*(?P<attr>[\w:-]+)\s*(?:(?P<op>[~^$*]?=)\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\]\s]+))\s*)?\]
""", re.VERBOSE)


def _parse_compound_list(selector: str) -> list[tuple[str, dict]]:
    """Return [(combinator, compound), ...]; the first combinator is ''."""
    parts: list[tuple[str, dict]] = []
    comb = ""
    compound: dict | None = None
    pos = 0
    s = selector.strip()
    if not s:
        raise SelectorError("empty selector")
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise SelectorError("unsupported selector syntax at %r" % s[pos:])
        pos = m.end()
        if m.group("ws") is not None:
            if compound is None:
                raise SelectorError("selector cannot start with a combinator: %r" % selector)
            parts.append((comb, compound))
            compound = None
            comb = ">" if ">" in m.group("ws") else " "
            continue
        if compound is None:
            compound = {"tag": None, "id": None, "classes": [], "attrs": []}
        if m.group("tag"):
            if compound["tag"] or compound["id"] or compound["classes"] or compound["attrs"]:
                raise SelectorError("tag must come first in %r" % selector)
            compound["tag"] = m.group("tag").lower()
        elif m.group("id"):
            compound["id"] = m.group("id")
        elif m.group("cls"):
            compound["classes"].append(m.group("cls"))
        else:
            val = m.group("dq")
            if val is None:
                val = m.group("sq")
            if val is None:
                val = m.group("bare")
            compound["attrs"].append((m.group("attr").lower(), m.group("op"), val))
    if compound is None:
        raise SelectorError("selector ends with a combinator: %r" % selector)
    parts.append((comb, compound))
    return parts


def _match_compound(node: Node, c: dict) -> bool:
    if c["tag"] and c["tag"] != "*" and node.tag != c["tag"]:
        return False
    if c["id"] and node.attrs.get("id") != c["id"]:
        return False
    if c["classes"]:
        have = set(node.classes)
        if not all(cls in have for cls in c["classes"]):
            return False
    for name, op, val in c["attrs"]:
        if name not in node.attrs:
            return False
        actual = node.attrs[name]
        if op is None:
            continue
        if op == "=" and actual != val:
            return False
        if op == "~=" and val not in actual.split():
            return False
        if op == "^=" and not actual.startswith(val):
            return False
        if op == "$=" and not actual.endswith(val):
            return False
        if op == "*=" and val not in actual:
            return False
    return True


def _match_chain(node: Node, chain: list[tuple[str, dict]], idx: int) -> bool:
    comb, compound = chain[idx]
    if not _match_compound(node, compound):
        return False
    if idx == 0:
        return True
    if comb == ">":
        parent = node.parent
        return parent is not None and parent.tag != "#document" and _match_chain(parent, chain, idx - 1)
    for anc in node.ancestors():
        if anc.tag == "#document":
            break
        if _match_chain(anc, chain, idx - 1):
            return True
    return False


def select(root: Node, selector: str) -> list[Node]:
    """Return elements matching ``selector`` in document order (outermost only)."""
    chains = [_parse_compound_list(part) for part in selector.split(",")]
    found = [n for n in root.iter()
             if n.tag != "#document" and any(_match_chain(n, ch, len(ch) - 1) for ch in chains)]
    chosen = set()
    result = []
    for node in found:
        if any(id(a) in chosen for a in node.ancestors()):
            continue
        chosen.add(id(node))
        result.append(node)
    return result


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _is_hidden(node: Node) -> bool:
    if "hidden" in node.attrs:
        return True
    if node.attrs.get("aria-hidden", "").lower() == "true":
        return True
    style = node.attrs.get("style", "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def _is_chrome(node: Node) -> bool:
    if node.tag in CHROME:
        return True
    if node.attrs.get("role", "").lower() in CHROME_ROLES:
        return True
    if node.tag in ("header", "footer"):
        # Site-level banner/footer only: nearest sectioning ancestor is <body>.
        for anc in node.ancestors():
            if anc.tag in SECTIONING:
                return anc.tag == "body"
        return True
    return False


def main_content_roots(root: Node) -> list[Node]:
    mains = [n for n in root.find_all("main") if not _is_hidden(n)]
    if mains:
        return [mains[0]]
    role_main = [n for n in root.iter() if n.attrs.get("role", "").lower() == "main"]
    if role_main:
        return [role_main[0]]
    articles = [n for n in root.find_all("article")
                if not any(a.tag == "article" for a in n.ancestors())]
    if articles:
        return articles
    bodies = root.find_all("body")
    return [bodies[0]] if bodies else [root]


_WS = re.compile(r"\s+")


def _node_text(start: Node, out: list[str]) -> None:
    # Strings on the stack are either source text (collapsed to single spaces
    # unless inside <pre>) or the structural "\n" / " " markers pushed below.
    stack: list = [start]
    while stack:
        item = stack.pop()
        if isinstance(item, tuple):
            text, pre = item
            out.append(text if pre else _WS.sub(" ", text))
            continue
        if isinstance(item, str):
            out.append(item)
            continue
        if item is not start and (_is_hidden(item) or _is_chrome(item)):
            continue
        tag = item.tag
        if tag == "br":
            out.append("\n")
            continue
        if tag == "img":
            continue
        if tag in BLOCK:
            out.append("\n")
            stack.append("\n")
        elif tag in CELL:
            out.append(" ")
            stack.append(" ")
        strings = [c for c in item.children if isinstance(c, str)]
        pre = bool(strings) and (tag == "pre" or any(a.tag == "pre" for a in item.ancestors()))
        stack.extend(reversed([(c, pre) if isinstance(c, str) else c for c in item.children]))


def extract_text(html: str, selector: str | None = None) -> list[str]:
    """Return the readable, whitespace-normalized text lines of the main content.

    Raises SelectorError when ``selector`` is invalid or matches nothing.
    """
    root = parse_html(html)
    if selector:
        roots = select(root, selector)
        if not roots:
            raise SelectorError("selector %r matched nothing" % selector)
    else:
        roots = main_content_roots(root)
    chunks: list[str] = []
    for node in roots:
        chunks.append("\n")
        _node_text(node, chunks)
    lines = []
    for line in "".join(chunks).replace("\xa0", " ").split("\n"):
        line = _WS.sub(" ", line).strip()
        if line:
            lines.append(line)
    return lines
