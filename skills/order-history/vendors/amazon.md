<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Amazon

Store ID `amazon`. Read by `order_history/vendors/amazon.py`.

**Terms:** **DSAR** ("data subject access request") is Amazon's *Request My Data*
export, a zip of folders of CSV files. **ASIN** is Amazon's ten-character product ID
(for books, usually the ISBN-10).

## Getting the export

On amazon.com, the user opens the *Request My Data* page (signed in; Amazon's help pages
link to it), asks for **Your Orders** (or everything), and confirms the request by email.
A download link arrives by email. Amazon says it can take up to a month; in practice it
has come within an hour of confirming. The download page needs the user's own login: let
them fetch the zip, then import it as it is (`order-history import <zip>`), with no need
to unzip it.

### With a browser

When you can drive the user's browser (Claude in Chrome, or any tool that works in the
user's own signed-in browser) you can do the navigating and waiting. Amazon makes the user
**sign in again on each link opened from its emails**, so this can't run unattended: you
stop and ask the user at each sign-in. Never type a password, a one-time code or any other
credential, and leave the request's own submit and confirm steps to the user.

1. Open `https://www.amazon.com/hz/privacy-central/data-requests/create.html?data-category=orders`
   in a tab you can read. The `data-category=orders` parameter selects *Your Orders*. Ask
   the user to submit the request there. The page then reads "You're almost done": a
   confirmation link has gone to their email and is valid for 5 days.
2. **Without access to the user's email, stop here.** Tell the user what comes next:
   confirm the request from the email, wait for a second email saying the data is ready,
   download `Your Orders.zip` from its link, and give you the zip's path. Then import it
   as below.
3. With read access to their email (for example a Gmail connector), find the
   confirmation: sender `dsar-request@amazon.com`, subject "Your Data Request
   Confirmation". Its link is `…/data-requests/confirm.html?requestId=<id>&signature=…`;
   note the `requestId`. Ask the user to open that link in the tab you can read and sign
   in. Loading the page confirms the request (there is no button), and the page then reads
   "We've received and are processing your request".
4. Wait for the completion email: same sender, subject "Your Data Request", with a
   "Download Data" link to `…/data-requests/view.html?requestID=<id>` (note `ID` in
   capitals there) that is valid for 90 days. Check every 5 minutes, for up to 60 minutes;
   if it hasn't come by then, stop and tell the user to say when it arrives. **Match on the
   request ID, not the email thread:** later emails join the thread of earlier ones, and a
   thread search can list only the thread's first email, so read the whole thread and take
   the newest email whose link holds the same ID.
5. Ask the user to open the download link in the tab and sign in. The page ("Download your
   Amazon data") lists `Your Orders.zip` and `FileDescriptions.csv`, each with a
   "Download" link to `…/data-requests/download.html?…&filename=Your+Orders.zip&id=<id>`.
   Download the zip. The browser saves it in the user's downloads folder, adding ` (2)`,
   ` (3)` and so on to the name when an older copy is there, so take the newest
   `Your Orders*.zip` modified after the download started.
6. Import it: `order-history import <zip> --dry-run --json`, report the changes, and run
   the real import when the user agrees (see SKILL.md's "Importing an export").

The export is cumulative: a newer one holds every earlier order, so it replaces the
current one. `import` archives the old one under `amazon/archive/<date>/`, and its report
lists titles that changed. Newer exports have blanked some digital product names to
`Not Applicable` (reported as `titles_blanked`); the archived export is then the only
remaining copy of those names, so never delete an archive.

## What is in it

The zip unpacks, under `<data>/amazon/current/`, to:

```
Your Amazon Orders/
├── Order History.csv            ★ every physical order item; the main file
├── Digital Content Orders.csv   Kindle books, apps, digital purchases
├── Digital Borrowed Items.csv   Kindle/Prime lending-library loans
├── Digital Returns.csv          refunds on digital purchases
├── Cart History.csv             items added to the cart (not necessarily bought)
├── Delivery Photos.csv          index of the driver's photo-on-delivery shots
└── Media/YourOrders.PhotoOnDelivery/media/
    └── <Photograph ID>.jpeg     delivery photos, named by UUID
Your Returns & Refunds/
├── Returns Status.csv           return contracts: reason, resolution, amounts
├── Refund Details.csv           refund payments: amount, date, status
├── Replacement Orders.csv       maps the original Order ID to the Replacement Order ID
└── Return Requests.csv          return requests with reason codes
Additional Data/
├── Retail.TransactionalInvoicing.*/   invoice PDFs
├── Your Orders.Returns.1/             refund records, plus README.txt (a field glossary)
├── YourOrders.CustomerReviews.1.1/    product reviews the user wrote
└── Sustainability.Value.Metrics.1/    one row of sustainability metrics
```

The tool reads only the first two CSVs; `import` recognizes the export by
`Your Amazon Orders/Order History.csv`. The rest is there for questions the commands
don't answer (returns, refunds, delivery photos), read as described under "Reading the
raw files".

### `Your Amazon Orders/Order History.csv`

- One row per item shipment: an order with 3 items has 3 rows.
- Key columns: `Order Date` (ISO 8601, UTC), `Order ID` (like `111-1234567-1234567`),
  `Product Name`, `ASIN`, `Order Status`, `Original Quantity`, `Unit Price`,
  `Total Amount`, `Currency`, `Shipping Address`, `Carrier Name & Tracking Number`,
  `Ship Date`, `Payment Method Type`, `Website`, and (exports from late 2026 on)
  `Department`, the product category, which the loader reads when present.
- `Website` holds the marketplace (`Amazon.com`, `Amazon.co.uk`, …) and sometimes
  internal codes. Check `Currency` before assuming USD.
- `Order Status` is the payment state, and it is **order-level**: a row whose item has
  already shipped can still show `Authorized` if another item in the order hasn't.
  - `Closed`: fully shipped and charged; the final state, and nearly every row.
  - `Authorized`: a card hold placed but not fully captured; the order was still in
    flight when the export was taken. The tool shows it as `In progress`.
  - `Cancelled`: cancelled before fulfillment, never charged.
  - `Digital Content Orders.csv` uses `SUCCESS` instead of `Closed`. The tool shows no
    status for `Closed` and `SUCCESS`.

### `Your Amazon Orders/Digital Content Orders.csv`

A much wider schema. The useful columns are `Order Date`, `Order ID`, `Product Name`,
`ASIN`, `Price`, `Price Currency Code`, `Marketplace`. Digital orders use their own Order
ID space, separate from physical ones.

## Joining the files

- **`Order ID`** joins `Order History.csv`, `Returns Status.csv`, `Refund Details.csv`,
  `Replacement Orders.csv`, `Return Requests.csv` and
  `Additional Data/Your Orders.Returns.1/`. Digital orders join
  `Digital Content Orders.csv` to `Digital Returns.csv`.
- **`ASIN`** identifies the product:
  - product page: `https://www.amazon.com/dp/<ASIN>`
  - order details (needs the user's login):
    `https://www.amazon.com/gp/your-account/order-details?orderID=<Order ID>`
- **`Photograph ID`** in `Delivery Photos.csv` is the file name (without `.jpeg`) under
  `Media/YourOrders.PhotoOnDelivery/media/`. That CSV has the delivery date and GPS
  coordinates but **no Order ID**: match photos to orders by comparing its date with
  `Ship Date`.

## Product images

`<data>/amazon/images.json` caches one entry per ASIN, filled by
`order-history update --amazon-images` (only when the user asks: it scrapes amazon.com
product pages, which may be against Amazon's conditions of use). Without the flag no
request goes to any Amazon host. Entries:

- `{"src": "i", "id": "<imageId>"}`: the image is
  `https://m.media-amazon.com/images/I/<imageId>._SL160_.jpg`, a stable CDN URL (any
  `_SL<px>_` size works).
- `{"src": "p"}`: `https://images-na.ssl-images-amazon.com/images/P/<ASIN>.01._SL250_.jpg`
  works. That endpoint is reliable for books (ISBN-style ASINs); for modern `B0…` ASINs it
  often answers HTTP 200 with a 1×1 placeholder GIF (43 bytes), so judge it by the image's
  size, never by the status code.
- `{"src": null}`: no image found (the product page is gone or has none).
- `{"src": "tbd"}`: probed, waiting for a product-page lookup; the next update continues.

The lookup probes the `P/` endpoint first (8 at a time), then fetches
`https://www.amazon.com/dp/<ASIN>` one page at a time, about 2 seconds apart, and reads
the `"hiRes":"https://m.media-amazon.com/images/I/…"` or `data-old-hires` value. A
captcha, 403, 429 or any 5xx or network error stops the run; nothing is recorded for that
ASIN.

## Reading the raw files

For questions the commands don't answer, read the CSVs under `<data>/amazon/current/`.
Run these from that folder, and quote every path: they contain spaces.

**Never split these files on commas or lines** (`cut`, `awk`, `split(",")`). Fields hold
quoted commas and embedded newlines (gift messages and addresses wrap across lines, so a
file has more lines than records), and naive splitting silently returns pieces of the
wrong field. `rg -i "<term>" "Your Amazon Orders/Order History.csv"` is fine for finding
*whether* something is there; for anything structured use Python's `csv` module:

```bash
python3 -c '
import csv, sys
term = sys.argv[1].lower()
with open("Your Amazon Orders/Order History.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if term in r["Product Name"].lower():
            print(r["Order Date"][:10], r["Order ID"], r["Total Amount"], r["Currency"], r["Product Name"][:80])
' "search term"
```

Every field of one order:

```bash
python3 -c '
import csv, sys
with open("Your Amazon Orders/Order History.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["Order ID"] == sys.argv[1]:
            print({k: v for k, v in r.items() if v not in ("Not Available", "Not Applicable", "")})
' "111-1234567-1234567"
```

Remember the privacy note in SKILL.md: print only the columns the question needs.

## Gotchas

- **Embedded newlines** in quoted fields: line counts are not record counts.
- **Sentinel values**: empty fields hold `Not Available` or `Not Applicable`, not empty
  strings.
- **Excel-armored negatives**: discount fields write negative numbers as `'-2.2'` (a
  leading apostrophe inside the quotes). Strip the `'` before parsing.
- **Thousands separators**: some amounts are written `1,234.56`.
- **BOM**: the CSVs under `Additional Data/` start with a UTF-8 byte-order mark. Open
  them with `encoding="utf-8-sig"` or the first column's name comes out corrupted.
- **Several currencies**: orders from other marketplaces are in GBP, EUR and so on.
- **`Additional Data/Your Orders.Returns.1/README.txt`** is Amazon's own glossary of
  refund statuses, destinations and failure reasons. Read it before interpreting that
  folder's CSV.
- **Spaces in paths**: always quote them in shell commands.
