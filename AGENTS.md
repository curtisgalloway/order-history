<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history search

Tools for searching your own order history, built from the data exports that
stores let you download. Amazon's "Request My Data" export and Adafruit's
order-history CSV are supported. The exports themselves are never committed;
they sit in this checkout, ignored by git (see `.gitignore`).

**If `LOCAL.md` exists, read it first.** It is gitignored and records facts
about the exports in this particular checkout (whose account, retrieval
dates, row counts). Keep personal facts there, never in tracked files: this
repo is meant to be publishable.

Terms used below (full list in `GLOSSARY.md`): **DSAR** is Amazon's "Request
My Data" export; **ASIN** is Amazon's product ID.

## Directory structure

Paths are relative to the repo root. The export folders are created by
unzipping the downloads here; they are not in git.

```
./
├── AGENTS.md, README.md, GLOSSARY.md, LICENSE
├── LOCAL.md                         ← (gitignored) facts about these exports
├── archive/                         ← (gitignored) earlier exports, replaced by newer ones
├── skills/order-history/scripts/
│   ├── order-history                ← the command-line tool (init, import, search, build, …)
│   └── order_history/               ← its package: vendors/, store.py, page.py, …
├── web/                             ← Vite + React + TypeScript source of the page shell
├── tests/                           ← unit tests, invented fixtures only
├── Adafruit/
│   ├── order_history.csv            ← Adafruit account export (order-level only)
│   ├── items.json                   ← item lines per order, from the item fetcher
│   └── lookup_email.txt             ← account email for the order-status lookup
├── Your Amazon Orders/
│   ├── Order History.csv            ← ★ the main file: all physical orders
│   ├── Digital Content Orders.csv   ← Kindle books, apps, digital purchases
│   ├── Digital Borrowed Items.csv   ← Kindle/Prime lending-library loans
│   ├── Digital Returns.csv          ← refunds on digital purchases
│   ├── Cart History.csv             ← items added to cart (not necessarily bought)
│   ├── Delivery Photos.csv          ← index of driver photo-on-delivery shots
│   └── Media/YourOrders.PhotoOnDelivery/media/
│       └── <Photograph ID>.jpeg     ← delivery photos, named by UUID
├── Your Returns & Refunds/
│   ├── Returns Status.csv           ← return contracts: reason, resolution, amounts
│   ├── Refund Details.csv           ← refund payments: amount, date, status
│   ├── Replacement Orders.csv       ← maps original Order ID → Replacement Order ID
│   └── Return Requests.csv          ← return requests with reason codes
└── Additional Data/
    ├── Retail.TransactionalInvoicing.*/   ← invoice PDFs
    ├── Your Orders.Returns.1/             ← refund records + README.txt field glossary
    ├── YourOrders.CustomerReviews.1.1/    ← product reviews you wrote
    └── Sustainability.Value.Metrics.1/    ← single-row sustainability metrics
```

## Amazon: `Your Amazon Orders/Order History.csv`

- One row per item-shipment: an order with 3 items has 3 rows.
- Key columns: `Order Date` (ISO 8601 UTC), `Order ID`
  (e.g. `111-1234567-1234567`), `Product Name`, `ASIN`, `Order Status`,
  `Original Quantity`, `Unit Price`, `Total Amount`, `Currency`,
  `Shipping Address`, `Carrier Name & Tracking Number`, `Ship Date`,
  `Payment Method Type`, `Website`, and (exports from late 2026 on)
  `Department`, the product category; the Amazon vendor module reads it
  when present.
- `Website` holds the marketplace (`Amazon.com`, `Amazon.co.uk`, …) and
  sometimes internal codes. Check `Currency` before assuming USD.
- `Order Status` values (payment lifecycle, **order-level** — a row whose item
  already shipped can still show `Authorized` if a sibling item hasn't):
  - `Closed` — fully shipped and charged; terminal state (the vast majority)
  - `Authorized` — card hold placed but not fully captured; order still
    in flight when the export was taken
  - `Cancelled` — cancelled before fulfillment, never charged
  - (`Digital Content Orders.csv` uses `SUCCESS` instead of `Closed`)
  - The search UI hides the default states (`Closed`/`SUCCESS`) and renders
    `Authorized` as an "In progress" stamp.

`Digital Content Orders.csv` has its own much wider schema; the useful columns
are `Order Date`, `Order ID`, `Product Name`, `ASIN`, `Price`,
`Price Currency Code`, `Marketplace`.

## Adafruit: `Adafruit/order_history.csv`

From adafruit.com's account order-history download. **One row per order, no
item lines**: totals (`subtotal`, `shipping`, `tax`, `coupon`,
`gift_certificate`, `total`, `refund`), shipping method, and delivery/billing
addresses.

- The export writes `-` as a space: an order ID comes out as
  `1234567 1234567890` and a date as `2024 01 31 12:00:00`. The Adafruit
  vendor module puts the hyphens back (`1234567-1234567890`, `2024-01-31`), which matches how
  adafruit.com's order-status page shows them. Times are store-local, not
  UTC (the page shows `12:00:00` as "12:00 PM").
- `shipping_method` holds HTML (sometimes truncated) with `=` also mangled to
  spaces; the vendor module strips the tags.
- Item lists are not in the CSV. A fetcher gets them (it was
  `fetch_adafruit_items.py`, removed with the old page in M3 and returning as
  `order-history update` in M4; see git history before M3) from Adafruit's guest "Order Status" form (on the account sign-in page),
  which shows an order's items given the account email and full order
  number, with no login: a POST of `email` and `order_number` to
  `https://www.adafruit.com/index.php?main_page=account_history_info`. Each
  item line on that page is a `div.row.confirm-cart.mobile-text-wrapper`
  holding the product link, `PID: <n>`, image, unit price, quantity and line
  total. Results are cached in `items.json`; the vendor module merges them,
  and orders not yet fetched show "item list not in export".
- The fetcher is deliberately polite: it reads robots.txt with its own
  User-Agent (Adafruit answers Python's default one with 403, which Python's
  `RobotFileParser.read()` turns into "disallow everything") and stops if
  the page is disallowed or robots.txt can't be read; it sends one request
  at a time, at least 10 s apart plus jitter (longer if robots.txt sets a
  `Crawl-delay`), never refetches a cached order, and stops at the first
  429/5xx. Keep it that way.

### Replacing an export with a newer one

Amazon's export is cumulative, so a newer one replaces the old folders
wholesale. Before replacing, move the old folders into
`archive/<store>-<retrieval date>/` rather than deleting them, and compare the
two: newer exports have blanked some digital product names to
`Not Applicable`, and the archive is the only remaining copy of those names.

## How to search

Run these from the repo root.

### Quick lookup: ripgrep

Fine for *finding* whether/where something exists (case-insensitive):

```bash
rg -i "soldering iron" "Your Amazon Orders/Order History.csv"
rg -i "<order id>" "Your Amazon Orders"
rg -i "<term>" -g '*.csv' .
```

### Anything structured: parse the CSV properly

**Do NOT use `cut`/`awk`/naive comma-splitting on these files.** Fields contain
quoted commas AND embedded newlines (gift messages and addresses wrap across
lines, so line counts are larger than record counts). Naive splitting silently
returns fragments of the wrong field. Use Python's `csv` module:

```bash
python3 -c '
import csv, sys
term = sys.argv[1].lower()
with open("Your Amazon Orders/Order History.csv", newline="") as f:
    for r in csv.DictReader(f):
        if term in r["Product Name"].lower():
            print(r["Order Date"][:10], r["Order ID"], r["Total Amount"], r["Currency"], r["Product Name"][:80])
' "search term"
```

Look up a full order by ID:

```bash
python3 -c '
import csv, sys
with open("Your Amazon Orders/Order History.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["Order ID"] == sys.argv[1]:
            print({k: v for k, v in r.items() if v not in ("Not Available", "Not Applicable", "")})
' "111-1234567-1234567"
```

### Search tool (web UI)

The page is a self-contained `index.html` in the data folder with live search
over every store's orders, including product thumbnails. Filters: store,
physical/digital, and an Items/Orders view (Orders groups items under one card
per order and highlights the matching items). The list is virtualized, so
thousands of rows scroll without paging. Open it directly — no server needed;
the data is embedded. `order-history import` rebuilds it; to rebuild by hand:

```bash
skills/order-history/scripts/order-history build
```

How it fits together:

- Each store is a vendor module (`order_history/vendors/<store>.py`) returning
  orders in one normalized shape (documented on `model.new_order()`). A store
  with no imported export is skipped.
- `web/` builds the **page shell**: the page with its
  `<script id="order-data" type="application/json">` element left empty.
  `order_history/page.py` puts the data in (every `<` escaped as `\u003c`) and
  writes `<data>/index.html` atomically. The data carries a `format` number;
  `page.py`'s `FORMAT` and `web/src/load.ts`'s `DATA_FORMAT` must change
  together, and a page whose numbers differ shows a message instead.
- The shell comes from the cache (`~/.cache/order-history/`), else a local
  `npm run build` in `web/` (a checkout with npm), else the `page-shell.html`
  attached to the GitHub release for this version (then cached). With none,
  the build exits 4 and the old page stays. `release.yml` attaches the shell
  when a `v*` tag is pushed; the tag must be `v` + `order_history.__version__`.
- To add a store: write its vendor module, list it in `vendors/__init__.py`,
  and add a `--store-<id>` color in `web/src/styles.css`.
- Page checks: `npm --prefix web ci && npm --prefix web run build`, then
  `npm --prefix web test` (runs `tests/search_cases.json` against
  `web/src/search.ts`, so the page and `search.py` can't drift).
- npm dependencies are pinned to exact versions (each one at least two weeks
  old when chosen) with a lockfile.
- The built page holds purchase data and lives only in the data folder,
  outside the checkout. `web/dist/` (the empty shell) is gitignored too.

## Cross-referencing (join keys)

- **`Order ID`** is the join key across `Order History.csv`,
  `Returns Status.csv`, `Refund Details.csv`, `Replacement Orders.csv`,
  `Return Requests.csv`, and `Additional Data/Your Orders.Returns.1/`.
  Digital orders use their own Order ID space (`Digital Content Orders.csv` ↔
  `Digital Returns.csv`).
- **`ASIN`** identifies the product. Useful URLs:
  - Product page: `https://www.amazon.com/dp/<ASIN>`
  - Order details: `https://www.amazon.com/gp/your-account/order-details?orderID=<Order ID>`
  - Product image (no auth, three tiers of reliability):
    1. `images.json` — local cache, built by an image fetcher (it was
       `fetch_images.py`, removed in M3; returning as `order-history update
       --amazon-images` in M4).
       `{"src": "i", "id": "<imageId>"}` means
       `https://m.media-amazon.com/images/I/<imageId>._SL160_.jpg` (stable CDN
       URL, any `_SL<px>_` size tag works); `{"src": "p"}` means tier 2 works;
       `{"src": null}` means no image found.
    2. `https://images-na.ssl-images-amazon.com/images/P/<ASIN>.01._SL250_.jpg` —
       reliable for books (ISBN-style ASINs); for modern `B0…` ASINs it often
       returns a 1×1 placeholder GIF (43 bytes) with HTTP 200, so check
       image dimensions/size, not status code.
    3. Scrape `https://www.amazon.com/dp/<ASIN>` with a browser User-Agent and
       extract `"hiRes":"https://m.media-amazon.com/images/I/…"` or
       `data-old-hires` — this is what the image fetcher automates (rate-limited,
       captcha-aware, resumable).
- **`Photograph ID`** in `Delivery Photos.csv` is the filename (without
  `.jpeg`) under `Media/YourOrders.PhotoOnDelivery/media/`. The CSV has the
  delivery date and GPS coordinates; it does **not** carry an Order ID, so
  match delivery photos to orders by comparing dates against `Ship Date`.

## Gotchas

- **Embedded newlines in quoted fields** — line counts ≠ record counts; see above.
- **Sentinel values**: empty-ish fields hold `Not Available` or
  `Not Applicable`, not empty strings.
- **Excel-armored negatives**: discount fields encode negative numbers as
  `'-2.2'` (leading apostrophe inside quotes). Strip `'` before parsing floats.
- **Thousands separators**: some amounts are written `1,234.56`.
- **BOM**: CSVs under `Additional Data/` start with a UTF-8 BOM — open with
  `encoding="utf-8-sig"` in Python or the first column name will be corrupted.
- **Multiple currencies**: orders from other marketplaces are GBP/EUR/etc.
- **`Additional Data/Your Orders.Returns.1/README.txt`** is Amazon's own
  glossary for refund statuses, destinations, and failure reasons — read it
  before interpreting that CSV.
- Export paths contain spaces — always quote them in shell commands.

## Before committing

This repo is meant to be publishable. Before every commit, check the staged
diff for personal data: email addresses, home-directory paths, real order
IDs, product names from the exports, addresses, and counts or dates that
describe one account. Use made-up examples (`111-1234567-1234567`) instead.
