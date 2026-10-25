<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Adafruit

Store ID `adafruit`. Read by `order_history/vendors/adafruit.py`.

## Getting the export

Signed in on adafruit.com, the user opens their account's **Order History** and
downloads it as CSV. Import the file as it is: `order-history import <file>.csv`. It is
recognized by its header (the columns `order_id`, `date_purchased`, `order_status`,
`subtotal`, `shipping`, `tax`, `coupon`, `gift_certificate`, `total`,
`shipping_method`), not by its name. Like Amazon's, a newer export holds every earlier
order and replaces the current one; the old one is archived under
`adafruit/archive/<date>/`.

## What is in it

`<data>/adafruit/current/order_history.csv` has **one row per order and no item lines**:
totals (`subtotal`, `shipping`, `tax`, `coupon`, `gift_certificate`, `total`,
`refund`), the shipping method, and delivery and billing addresses. So import reports
always show 0 items for Adafruit; the item lists come from `update`.

Quirks the loader undoes:

- The export writes `-` as a space: an order ID comes out as `1234567 1234567890` and a
  date as `2024 01 31 12:00:00`. The loader puts the hyphens back
  (`1234567-1234567890`, `2024-01-31`), which is how adafruit.com's order-status page
  shows them; use that form with `order-history order`. Times are store-local, not UTC
  (the page shows `12:00:00` as "12:00 PM").
- `shipping_method` holds HTML, sometimes cut off, with `=` also turned into spaces. The
  loader strips the tags.

When reading the CSV yourself, use Python's `csv` module (as in `amazon.md`), never comma
splitting: addresses hold quoted commas.

## Item lists: `update`

`order-history update` fills `<data>/adafruit/items.json` (order ID →
`{"fetched": ..., "items": [...]}`) from Adafruit's guest **Order Status** form, the one on
the account sign-in page. It shows an order's items given the account email and the full
order number, with no login: a POST of `email` and `order_number` to
`https://www.adafruit.com/index.php?main_page=account_history_info`. Each item line on the
result page is a `div.row.confirm-cart.mobile-text-wrapper` holding the product link,
`PID: <n>`, the image, unit price, quantity and line total. An order not fetched yet shows
"item list not in export" on the page and an empty `items` list in `--json`.

The email comes from `--email`, then `$ADAFRUIT_EMAIL`, then
`<data>/adafruit/lookup_email.txt` (one line). It is needed only when some order lacks
items; with none, `update` exits 3 and says so.

The lookup is deliberately polite, and must stay so:

- It reads robots.txt first, with its own User-Agent, and stops (exit 20) if the lookup
  page is disallowed or robots.txt can't be read. (Adafruit answers Python's default
  User-Agent with 403, which Python's `RobotFileParser.read()` would turn into "disallow
  everything".)
- One request at a time, at least 10 seconds apart plus up to half that again of random
  jitter, or longer if robots.txt sets a `Crawl-delay`.
- An order already in `items.json` is never fetched again.
- It stops at the first 429 or 5xx rather than retrying (exit 20 if nothing was saved
  yet, 21 if some was). Run `update` again later; it continues where it stopped.
- A lookup that fails for one order (another HTTP error such as a 404, a network error,
  a page that isn't that order's) is skipped, counted in `failed`, and asked again on
  the next run. Failures also make the exit 20 or 21.

Don't send these lookups any other way (a browser tool, `curl`, a loop of your own), and
don't lower the delay: the rules exist so a personal archive never looks like a scraper.
The project's tests check each rule with the network and clock stubbed; nothing in them
contacts the store.
