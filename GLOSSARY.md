<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Glossary

Plain-language meanings of the terms used in this repo.

**ASIN** — Amazon Standard Identification Number: Amazon's ten-character
product ID (for books it is usually the ISBN-10). It appears in Amazon's
export and builds product-page and image URLs.

**DSAR** — Data Subject Access Request: a request for the personal data a
company holds on you. Amazon's version is the *Request My Data* page; the
result is a zip of folders such as `Your Amazon Orders/`.

**Crawl-delay** — an optional line in a site's `robots.txt` asking automated
clients to wait that many seconds between requests. `update` waits at least
that long, or 10 s, whichever is longer.

**Enrichment** — what `order-history update` adds that an export leaves out:
Adafruit item lists, looked up one order at a time, and (only with
`--amazon-images`) Amazon product images. Results are kept in the store's
cache file (`items.json`, `images.json`) in the data folder, so nothing is
looked up twice.

**Export** — the file or files a store lets you download containing your own
order history. Each store's export has its own columns and quirks.

**Item** — one product line in an order (Amazon writes one CSV row per item).
Adafruit's export has no items, only order totals.

**Loader** — the part of a store's vendor module
(`order_history/vendors/<store>.py`) that reads that store's export and returns
orders in the shared shape the page understands.

**Order view / Items view** — the two ways the page lists results: one card
per order with its items inside, or one row per item.

**Page shell** — the search page built with no data in it: its
`<script id="order-data">` element is empty. The tool fills that element with
your orders to make `index.html`. Each release publishes it as
`page-shell.html`, so building the page needs no Node.

**robots.txt** — a file at a website's root saying which pages automated
clients may fetch. `update` reads Adafruit's before it looks up any order
(not on a dry run, or when nothing is missing) and stops if the lookup page
is disallowed or the file can't be read.

**Single-file build** — the page is built so its JavaScript, styles and data
are all inside one `index.html`, which therefore opens from disk with no web
server (done by `vite-plugin-singlefile`).

**Virtualized list** — the page renders only the rows currently on screen
and swaps them as you scroll, so thousands of results scroll smoothly.

**Vite** — the build tool that turns the TypeScript/React source in
`web/` into the page shell.
