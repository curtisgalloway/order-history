<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history search

Search everything you have ever bought online, across stores, in one local
page. You download your own order history from each store and import it with
one command. It produces a single `index.html` that opens straight from disk: live search, product thumbnails, a per-store filter,
and an items or one-card-per-order view. Nothing is uploaded anywhere.

**Terms** (more in [GLOSSARY.md](GLOSSARY.md)):

- **Export** — the file(s) a store lets you download with your own order
  history.
- **DSAR** — "data subject access request": Amazon's *Request My Data*
  export, a zip of CSV files.
- **ASIN** — Amazon's product ID, used to link to and show product images.
- **Page shell** — the search page with no data in it, published with each
  release; the tool fills in your orders.

## Supported stores

| Store | What to download | What you get |
| --- | --- | --- |
| Amazon | *Request My Data* → "Your Orders" (arrives as a zip, by email, after a few days) | Every item, physical and digital |
| Adafruit | Account → Order History → download CSV | One entry per order (item lists come with `update`, below) |

A store you haven't imported is skipped, so you can use either one alone.

## Use

Needs Python 3.10+. Node is not needed to build the page: the tool downloads
the page shell for its version once from this project's GitHub release and
caches it. (Until the first release is published, that download fails, so
building the page needs Node and npm, from this checkout.)

```bash
git clone <this repo> order-history
cd order-history
skills/order-history/scripts/order-history init
skills/order-history/scripts/order-history import ~/Downloads/<the export zip or CSV>
open ~/Documents/"Order History"/index.html
```

`init` creates the data folder (`~/Documents/Order History` unless you pass
`--data-dir`). `import` recognizes the store, keeps the previous export in
`archive/`, reports what changed, and rebuilds the page. `search`, `order`
and `status` answer questions from the command line (add `--json` for
agents), and `build` rebuilds the page by hand.

Adafruit item lists and Amazon product images come back with
`order-history update` in a later release; the old fetcher scripts were
removed with the old page.

## Your data stays out of git

Your exports, caches and the built page live in the data folder, outside this
checkout. `.gitignore` still covers the old in-checkout locations
(`Your Amazon Orders/`, `Adafruit/`, `search/`, `archive/`, `LOCAL.md`), so a
checkout that still holds data from before doesn't leak it. Check
`git status` before committing anyway.

## Development

- `skills/order-history/scripts/order_history/` — the tool: one vendor module
  per store, each turning that store's export into the same order/item shape;
  importing, searching, and `page.py`, which fills the page shell.
- `web/` — the page shell: React 19, TypeScript, Vite, and
  `vite-plugin-singlefile` to inline everything into one file. In a checkout
  with Node, `build` and `import` build the shell from here (`npm ci` on first
  use) instead of downloading it, so your edits show up.
- Checks: `python3 -m unittest discover -s tests`, and
  `npm --prefix web ci && npm --prefix web run build && npm --prefix web test`.
- Adding a store: write its vendor module, list it in `vendors/__init__.py`,
  and give it a badge color (`--store-<id>`) in `web/src/styles.css`.
  [AGENTS.md](AGENTS.md) documents the export formats and their quirks.

## License

Apache 2.0 — see [LICENSE](LICENSE).
