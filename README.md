<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history search

Search everything you have ever bought online, across stores, in one local
page. You download your own order history from each store, drop the files
into this folder, and run one command. It produces a single `index.html` that
opens straight from disk: live search, product thumbnails, a per-store filter,
and an items or one-card-per-order view. Nothing is uploaded anywhere.

**Terms** (more in [GLOSSARY.md](GLOSSARY.md)):

- **Export** — the file(s) a store lets you download with your own order
  history.
- **DSAR** — "data subject access request": Amazon's *Request My Data*
  export, a zip of CSV files.
- **ASIN** — Amazon's product ID, used to link to and show product images.

## Supported stores

| Store | What to download | Where it goes | What you get |
| --- | --- | --- | --- |
| Amazon | *Request My Data* → "Your Orders" (arrives as a zip, by email, after a few days) | Unzip into the repo root, so `Your Amazon Orders/` sits next to this README | Every item, physical and digital |
| Adafruit | Account → Order History → download CSV | `Adafruit/order_history.csv` | Every item, after `fetch_adafruit_items.py` (below); otherwise one entry per order |

A store whose export is missing is skipped, so you can use either one alone.

## Build

Needs Python 3.10+ and Node.js 20+.

```bash
git clone <this repo> order-history
cd order-history
python3 search/build.py
open search/index.html
```

The first build runs `npm ci` in `search/app/`. Re-run `build.py` whenever you
replace an export with a newer one.

### Adafruit items

Adafruit's CSV has order totals but no items. `search/fetch_adafruit_items.py`
looks each order up through Adafruit's guest order-status form (your account
email plus the order number, no password) and caches the items in
`Adafruit/items.json`:

```bash
echo you@example.com > Adafruit/lookup_email.txt
python3 search/fetch_adafruit_items.py
python3 search/build.py
```

It follows robots.txt, waits at least 10 seconds between requests, and only
fetches orders it hasn't fetched before, so it is safe to run from cron after
each new export. The email can also come from `--email` or `$ADAFRUIT_EMAIL`.

### Optional: Amazon product images

The page shows Amazon thumbnails by ASIN. Book ASINs mostly work out of the
box; for newer products, `search/fetch_images.py` looks each ASIN up once and
caches the image ID in `search/images.json`:

```bash
python3 search/fetch_images.py
python3 search/build.py
```

It fetches public amazon.com product pages, slowly and with random delays,
and stops if Amazon serves a captcha (run it again later to continue). Using
it is your call: automated access to amazon.com may be against Amazon's
conditions of use.

## Your data stays out of git

Everything that holds purchase data is in `.gitignore`: the store exports,
the generated `search/index.html`, `search/app/src/generated/`,
`search/images.json`, and `LOCAL.md` (notes about your particular exports).
Check `git status` before committing anyway.

## Development

- `search/build.py` — one loader per store, each turning that store's export
  into the same order/item shape, then the Vite build.
- `search/app/` — the page: React 19, TypeScript, Vite, and
  `vite-plugin-singlefile` to inline everything into one file.
- Live-reloading UI work:

  ```bash
  python3 search/build.py --data-only
  npm --prefix search/app run dev
  ```

- Adding a store: write a `load_<store>()` in `build.py`, add it to `STORES`,
  and give it a badge color (`--store-<id>`) in `search/app/src/styles.css`.
  [AGENTS.md](AGENTS.md) documents the export formats and their quirks.

## License

Apache 2.0 — see [LICENSE](LICENSE).
