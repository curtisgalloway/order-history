<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Glossary

Plain-language meanings of the terms used in this repo.

**Archive** — earlier exports kept in the data folder, under
`<store>/archive/<date>/`. `import` moves the current export there before installing a
newer one; the tool never deletes an archive.

**ASIN** — Amazon Standard Identification Number: Amazon's ten-character
product ID (for books it is usually the ISBN-10). It appears in Amazon's
export and builds product-page and image URLs.

**Crawl-delay** — an optional line in a site's `robots.txt` asking automated
clients to wait that many seconds between requests. `update` waits at least
that long, or 10 s, whichever is longer.

**Data folder** — the folder on your machine holding your imported exports, their
archives, the lookup caches and the built page (`index.html`). It is outside this
repository: `~/Documents/Order History` unless `init --data-dir`, `$ORDER_HISTORY_DIR`
or the config file (`~/.config/order-history/config.json`) says otherwise.

**DSAR** — Data Subject Access Request: a request for the personal data a
company holds on you. Amazon's version is the *Request My Data* page; the
result is a zip of folders such as `Your Amazon Orders/`.

**Enrichment** — what `order-history update` adds that an export leaves out:
Adafruit item lists, looked up one order at a time, and (only with
`--amazon-images`) Amazon product images. Results are kept in the store's
cache file (`items.json`, `images.json`) in the data folder, so nothing is
looked up twice.

**Export** — the file or files a store lets you download containing your own
order history. Each store's export has its own columns and quirks.

**Frontmatter** — the block between two `---` lines at the top of a `SKILL.md`, holding
the skill's `name` and `description`. Agents read it to decide when to load the skill.

**Item** — one product line in an order (Amazon writes one CSV row per item).
Adafruit's export has no items, only order totals.

**Loader** — the part of a vendor module that reads that store's export and returns
orders in the shared shape the page understands (`read()` and `load()`).

**Marketplace** — in Claude Code, a catalog of plugins that users add by its
repository (`.claude-plugin/marketplace.json`). This repository is a marketplace with
one plugin, itself.

**Model provider** — the company running the AI model behind a coding agent. Whatever
the agent reads, including this tool's search results, is sent to it.

**Order view / Items view** — the two ways the page lists results: one card
per order with its items inside, or one row per item.

**Page shell** — the search page built with no data in it: its
`<script id="order-data">` element is empty. The tool fills that element with
your orders to make `index.html`. Each release publishes it as
`page-shell.html`, so building the page needs no Node.

**Plugin** — Claude Code's install unit: a folder with a manifest
(`.claude-plugin/plugin.json`) and components such as skills. This repository is one;
its skill is `skills/order-history/`. Other agents use the skill folder directly.

**robots.txt** — a file at a website's root saying which pages automated
clients may fetch. `update` reads Adafruit's before it looks up any order
(not on a dry run, or when nothing is missing) and stops if the lookup page
is disallowed or the file can't be read.

**Single-file build** — the page is built so its JavaScript, styles and data
are all inside one `index.html`, which therefore opens from disk with no web
server (done by `vite-plugin-singlefile`).

**Skill** — a folder whose `SKILL.md` tells a coding agent how to do a task, here how
to drive `order-history`. Claude Code, Codex and Antigravity read the same format.
`order-history --skill` prints it.

**Staging folder** — `<store>/.staging-<time>/`, where `import` unpacks an export
before swapping it in. One left behind by an interrupted import is reported by `status`
and removed by the next import.

**uv tool** — [uv](https://docs.astral.sh/uv/)'s way of installing a Python
command-line program into its own environment and putting the command on `PATH`
(`uv tool install`).

**Vendor module** — one store's support: a Python module
(`order_history/vendors/<id>.py`) that detects, installs, reads and enriches that
store's export, plus an instruction file (`skills/order-history/vendors/<id>.md`)
telling an agent how to get the export and what its quirks are. The registry in
`vendors/__init__.py` lists them.

**Virtualized list** — the page renders only the rows currently on screen
and swaps them as you scroll, so thousands of results scroll smoothly.

**Vite** — the build tool that turns the TypeScript/React source in
`web/` into the page shell.
