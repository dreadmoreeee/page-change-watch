# page-change-watch

Watch web pages for **meaningful** changes: competitor price pages, terms and privacy pages, your own site after a deploy. It keeps noise-filtered text snapshots, prints a readable diff when something real changes, and **exits 1** so cron can tell you.

```
page-change-watch run -c watch.yml          # first run: baseline, then only real changes are reported
page-change-watch show competitor-pricing   # latest snapshot text
```

Why another change watcher:

- **Noise is filtered, not diffed.** Dates, times, "5 minutes ago", CSRF/nonce tokens, UUIDs, hex/base64 hashes and cache-busting query strings become placeholders, and scripts, styles, nav, site header/footer and hidden elements are dropped. A page that only re-rendered its timestamp is `unchanged`.
- **Main content only.** `<main>`, `role=main` or `<article>` when present, else `<body>`; or your own CSS selector per page.
- **Readable output.** Unified diff plus a word-level diff (`Pro [-$19-]{+$24+} per month`), as Markdown or JSON, and an optional self-contained HTML diff page.
- **Polite.** GET only, at least 1 s between requests, a clear User-Agent, and robots.txt honored with **RFC 9309** matching (longest rule wins), not `urllib.robotparser`'s first match.
- **No dependencies.** Standard library only, Python 3.10+. PyYAML is optional (JSON watch lists always work); Playwright is optional, for JavaScript pages.

## Measured result

Real run against three live sites, plain HTTP, default 1 s delay: a baseline, then a second run five minutes later ([examples/demark-watch.yml](examples/demark-watch.yml)). Report title and blank lines trimmed.

```
$ page-change-watch run -c examples/demark-watch.yml --store examples/.demo-store
Run: 2026-09-29T09:15:36.572704Z
Result: 3 page(s): 0 changed, 0 unchanged, 3 new, 0 error(s), 0 blocked by robots.txt

| Page | Result | HTTP | Lines | SHA-256 | Note |
|---|---|---|---|---|---|
| [demarkstudio](https://demarkstudio.ca) | new | 200 | 230 | `0ea795ffb125` |  |
| [riverside-pub](https://demo.demarkstudio.ca/riverside-pub/site) | new | 200 | 27 | `1f9037ad6505` |  |
| [portfolio](https://marvin.demarkstudio.ca) | new | 200 | 133 | `b9a37d507895` |  |
exit code: 0

$ page-change-watch run -c examples/demark-watch.yml --store examples/.demo-store --html examples/.demo-store/html
Run: 2026-09-29T09:20:45.048204Z
Result: 3 page(s): 0 changed, 3 unchanged, 0 new, 0 error(s), 0 blocked by robots.txt

| Page | Result | HTTP | Lines | SHA-256 | Note |
|---|---|---|---|---|---|
| [demarkstudio](https://demarkstudio.ca) | unchanged | 200 | 230 | `0ea795ffb125` | same as 2026-09-29T09:15:36.572704Z |
| [riverside-pub](https://demo.demarkstudio.ca/riverside-pub/site) | unchanged | 200 | 27 | `1f9037ad6505` | same as 2026-09-29T09:15:37.847705Z |
| [portfolio](https://marvin.demarkstudio.ca) | unchanged | 200 | 133 | `b9a37d507895` | same as 2026-09-29T09:15:39.683205Z |
exit code: 0
```

No change, as expected. Not every byte was identical, though: two consecutive fetches of each page returned **different raw HTML** every time, because Cloudflare re-keys its e-mail obfuscation on every response (`data-cfemail="b8fcddf5..."` and `/cdn-cgi/l/email-protection#85c1e0c8...`). Those hex keys live in attributes, and the visible text stays `[email protected]`, so the extracted text was byte-identical to the baseline and no built-in placeholder was even needed. A raw-HTML hash would have reported all three pages as changed on every run. The whole demonstration made 24 GET requests in total, at least 1 s apart.

Local demo of a detected change ([examples/local_demo.py](examples/local_demo.py), no internet): a pricing page on 127.0.0.1 whose second version changes only noise (timestamp, CSRF token, header banner, script state, cache-busting query, "x minutes ago") and whose third version changes the Pro price.

```
$ python examples/local_demo.py
=== run 1: baseline
Result: 1 page(s): 0 changed, 0 unchanged, 1 new, 0 error(s), 0 blocked by robots.txt
exit code: 0

=== run 2: noise only
Result: 1 page(s): 0 changed, 1 unchanged, 0 new, 0 error(s), 0 blocked by robots.txt
| [acme-pricing](http://127.0.0.1:52461/pricing) | unchanged | 200 | 7 | `4ee6b355f414` | same as 2026-09-29T09:22:40.538705Z |
exit code: 0

=== run 3: price change
Result: 1 page(s): 1 changed, 0 unchanged, 0 new, 0 error(s), 0 blocked by robots.txt

## acme-pricing: changed

### Word changes

- `...Starter $9 per month Pro [-$19-]{+$24+} per month Team $49 per...`

### Unified diff

--- previous 2026-09-29T09:22:40.538705Z
+++ current 2026-09-29T09:22:40.585704Z
@@ -3,5 +3,5 @@
 Plan Price
 Starter $9 per month
-Pro $19 per month
+Pro $24 per month
 Team $49 per month
 Session token: [token]
exit code: 1
```

Full samples: [examples/sample-report.md](examples/sample-report.md) and [examples/sample-diff.html](examples/sample-diff.html).

```
$ python -m pytest -q -p no:cacheprovider --import-mode=importlib
.........................................................                [100%]
57 passed in 13.52s
```

The tests need no internet: a local HTTP server on a random free port serves pages that change between runs (noise only, a real price change, selector scoping, custom ignore regexes, robots.txt disallow, HTML diff escaping), and one test renders a JavaScript page with Playwright (skipped when Chromium is unavailable).

## Install

```
pip install .                 # core
pip install ".[yaml]"         # YAML watch lists
pip install ".[render]"       # render: true / --render
playwright install chromium
```

## CLI

```
page-change-watch run -c watch.yml [--render] [--store DIR] [--format markdown|json] [--output FILE]
                                   [--html DIR] [--keep N] [--delay SECONDS] [--timeout SECONDS]
page-change-watch show NAME [--store DIR] [--normalized]
page-change-watch list [--store DIR]
python -m page_change_watch ...
```

- `--store` defaults to `.page-change-watch/`; `--keep` snapshots per page (default 10); `--delay` between requests (default 1 s); `--timeout` default 20 s.
- `--html DIR` writes one self-contained HTML diff page per changed page (no external assets, all page text escaped).
- The first run of a page is its baseline and is reported as `new`, not as a change.

| Exit code | Meaning |
|---|---|
| 0 | nothing changed (baselines included) |
| 1 | at least one page changed (errors, if any, are in the report too) |
| 2 | errors only (HTTP error, network, robots.txt disallow, selector matched nothing) or usage error |

## Watch list

YAML or JSON; `name` (or `id`) and `url` are required.

```yaml
defaults:
  ignore:
    - 'Visitors today: \d+'

pages:
  - name: competitor-pricing
    url: https://competitor.example/pricing
    selector: "main .pricing-table"
  - name: terms
    url: https://www.example.com/legal/terms
    ignore: ['Reference #\w+']
  - name: my-home-after-deploy
    url: https://www.example.com/
    render: true
  - id: opening-hours
    url: https://www.example.com/contact
    selector: "#hours"
    default_ignore: false
```

- `selector`: CSS selector for the content to watch. No match is an error, never a silent empty page.
- `ignore`: regexes removed from each text line before comparing (added to the built-in filters); a line that becomes empty is dropped.
- `render`: fetch with headless Chromium via Playwright (imported only when needed).
- `default_ignore: false`: turn off the built-in filters for this page, e.g. to watch opening hours like `10:00`.
- `defaults` applies to every entry; `ignore` lists are combined.

Same list as JSON: [examples/watch.json](examples/watch.json).

**Selectors** are implemented over the stdlib `html.parser` tree: `tag`, `*`, `#id`, `.class`, compounds like `div.price#main`, `[attr]`, `[attr=v]`, `[attr~=v]`, `[attr^=v]`, `[attr$=v]`, `[attr*=v]`, descendant (`main .price`) and child (`ul > li`) combinators, and comma groups. Pseudo-classes and sibling combinators raise an error. Nested matches count once (outermost element).

## Noise filters

| Placeholder | Matches |
|---|---|
| `[date]` | `2026-09-29`, `2026-09-29T10:11:12Z`, `09/29/2026`, `29.09.2026`, `2026/09/29`, `September 29, 2026`, `Sep 29`, `Tuesday, 29 September 2026` |
| `[time]` | `10:11`, `10:11:12`, `6:42 PM EST` |
| `[ago]` | `5 minutes ago`, `an hour ago`, `3 days ago`, `just now` |
| `[token]` | `csrf_token=...`, `nonce: "..."`, `Session token: ...`, mixed-case random strings of 20+ characters |
| `[hash]`, `[id]` | hex strings of 16+ characters, UUIDs |
| `[cache]` | `app.js?v=123`, `?ver=`, `?cb=`, `?t=`, `?_=`, `bundle.js?1695912345` |

Prices, phone numbers, version numbers, slugs and ordinary words are kept. Before this runs, `script`, `style`, `noscript`, `template`, `svg`, `iframe`, `nav`, `aside`, the site-level `header`/`footer` (nearest sectioning ancestor is `<body>`; an article's own header stays), `hidden`/`aria-hidden="true"` and inline `display:none` elements are dropped. Comparisons re-normalize the stored text with the current rules, so editing `ignore` never causes a false change.

## Snapshots

```
.page-change-watch/<page>/snapshots/<UTC timestamp>.json   baseline and every change (last --keep)
.page-change-watch/<page>/latest.txt                       readable text of the newest version
.page-change-watch/<page>/meta.json                        last check: time, HTTP status, result
```

A snapshot holds the readable text, the normalized text, its SHA-256, the UTC timestamp, the URL and final URL, the HTTP status and whether it was rendered.

## Politeness

- Every request (pages and robots.txt) is a GET with `User-Agent: page-change-watch/1.0 (+https://github.com/dreadmoreeee/page-change-watch)` and waits at least `--delay` seconds after the previous one.
- robots.txt is fetched once per host per run and matched for the product token `page-change-watch` with [rfc9309.py](page_change_watch/rfc9309.py) (a copy of robots9309, same author, MIT). A 4xx robots.txt allows everything; a 5xx or unreachable one disallows everything and is reported.
- It never submits forms, clicks or logs in. Render mode loads the page like a browser, so it also requests that page's own images, CSS and scripts.

## Cron

```
# 7:15 every morning; mail the report only when something changed (exit 1)
15 7 * * * cd /srv/watch && page-change-watch run -c watch.yml --html diffs/ -o report.md; [ $? -eq 1 ] && mail -s "Pages changed" me@example.com < report.md
```

## Limitations

- Plain mode sees the HTML the server sends; pages built by JavaScript need `render: true`.
- Text only: image, style and layout changes are not detected.
- The built-in time filter also hides real times such as opening hours; use `default_ignore: false` for such pages.
- Redirects are followed by urllib; robots.txt is checked for the original host only.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
