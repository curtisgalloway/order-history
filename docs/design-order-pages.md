<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Catching up from order pages — Design

Revision: 2026-10-25, draft for approval. Extends [design.md](design.md) (phase 2,
"Optional catching up between exports"); everything there still holds unless this
document says otherwise.

**Terms** (more in [GLOSSARY.md](../GLOSSARY.md)):

- **Export**: the file a store lets you download with your own order history.
- **`as_of`**: the newest order date in the current export.
- **Order list / details page**: Amazon's "Your Orders" page
  (`/gp/css/order-history`) and one order's page
  (`/gp/your-account/order-details?orderID=<id>`).
- **Catch-up**: the agent reading order pages in your signed-in browser and
  saving the orders the export doesn't have yet.
- **Saved order**: an order stored by catch-up, kept until an export contains it.

## Intent

An Amazon export takes about half an hour, needs you to sign in on each emailed link,
and can still miss an order placed minutes before it was built. Between exports, the
search answers "when did I buy X" with stale data. Amazon's order confirmation emails no
longer carry item details, so they can only tell us that something new exists.

Catch-up closes that gap without a new export: the agent opens your order list, finds
the orders the data folder lacks, reads each one's details page and hands the records to
`order-history add`. Observed 2026-10-25: both pages opened in the agent's browser tab
with no sign-in prompt, and the details page marks each part with a `data-component`
attribute, which is a much steadier hook than the layout.

## Goals, non-goals, anti-goals

Goals:

- **G1** Orders newer than the export can be added from order pages, with item names,
  ASINs, quantities, prices and the order total.
- **G2** A saved order looks and searches exactly like an exported one (user decision
  2026-10-25: "It should look the same as everything else").
- **G3** The next export takes over: an order ID present in the export replaces the
  saved copy, which is then dropped. Saved orders the export still lacks are kept.
- **G4** Catch-up runs only when you ask. When answering a question from data whose
  last refresh is more than 30 days old, the agent may suggest a refresh, once per
  conversation (user decision 2026-10-25). It may also suggest one, within the same
  once per conversation, when the user asks about a recent order that the search can't
  find although the data is not that old (user decision 2026-10-25, "Yes, suggest it";
  added in M8).

Non-goals:

- Catching up older changes: returns, refunds, cancellations or status changes of orders
  already in the export. A new export covers those.
- Digital orders (Kindle, apps). They live on other pages.
- Other stores. A store can opt in later (my call, below), but only Amazon gets a flow.
- Running on a schedule or on its own, and reading email bodies. Email is used only for
  message dates, as in the current "Is a new export worth it?" step.
- A browser automation script (Playwright or similar). The agent drives the user's own
  browser; the tool never talks to amazon.com.

Anti-goals (a failure even if it works):

- The agent types a password or code, or works around a sign-in or captcha.
- Saved orders look different from exported ones, or a stale saved copy hides the
  export's newer data for the same order.
- Anything from an order page reaches the repository.

## Constraints

- Standard library Python, 3.10+, as before. The tool sends no request to Amazon: the
  agent reads the pages and passes JSON in.
- Order pages need your signed-in session. If Amazon asks for a sign-in, the agent stops
  and waits for you.
- The page HTML can change without notice. The tool's input is a plain JSON document,
  so a page change only touches the skill's instructions, never stored data.
- The export folder (`current/`) is never written to by catch-up.

## Decided

- **Run only when asked** (user, G4). The skill's trigger is the user asking to
  refresh or catch up, or saying yes to the agent's once-per-conversation suggestion.
- **Saved orders look the same** (user, G2). Internally they carry
  `source: "order-page"`; the page and the search results do not mark them.
- **Order confirmation emails are a signal only** (user, 2026-10-25): with email
  access, a date after the export is a sign catch-up has something to find; finding
  none proves nothing (issue #14).

## How it works

### 1. Finding new orders (skill, browser)

1. `order-history status --json` gives the Amazon `as_of` and `checked`.
2. Open the order list in a tab the agent can read. It lists orders newest first, 10 per
   page. Collect order IDs until reaching one the data folder already has (in the export
   or saved); read the rest of that page too, since orders on one date can appear in any
   order. Stop after 3 pages (30 orders) and ask before going further. To tell whether
   an ID is known, run `order-history order <id> --json` for it: exit 0 means known,
   exit 1 means new. Saved orders count, since they are part of the loaded list. No new
   command is needed for this.
3. For each new ID, open the details page and read, using the `data-component` hooks
   (recorded in `vendors/amazon.md`; current values observed 2026-10-25):
   - `orderDate`, `orderId`;
   - per item in `purchasedItems`: title, ASIN (from the `/dp/<ASIN>` link), unit price,
     quantity (the badge on the item image; absent means 1);
   - `chargeSummary`: the grand total (the other rows are not stored; see
     "Same shape as an exported order");
   - `shipmentStatus` (for example "Arriving March 9", "Delivered").
4. Write the orders as one JSON document to a temporary file and run
   `order-history add <file> --dry-run --json`, report, then run it for real.

### 2. `order-history add`

```
order-history add FILE [--dry-run] [--json] [--data-dir PATH]
```

Input (`FILE`, or `-` for stdin):

```json
{"store": "amazon",
 "orders": [{"id": "111-1234567-1234567", "date": "2026-03-03", "currency": "USD",
             "total": "28.14", "status": "In progress",
             "items": [{"name": "Example USB cable", "asin": "B000000000",
                        "qty": "2", "unit": "12.99"}]}]}
```

- Fields are the existing order and item shape (`model.new_order`/`new_item`). The tool
  fills `source: "order-page"`, `store`, item `total` (unit × qty when missing) and item
  `url` (`https://www.amazon.com/dp/<ASIN>`), and runs amounts through `model.money`.
- `summary` is refused (exit 2): exported Amazon orders never have one (see below).
- Required: order `id` and `date` (YYYY-MM-DD), and each item's `name`. A document
  missing one, with an unknown store, or not valid JSON exits 2 and saves nothing.
- An order whose ID is already in the export is **skipped** and listed in the report
  (the export wins, G3). An ID already saved is **replaced** (a later read of the same
  order, for example after it shipped).
- An empty `orders` list is valid: it records that the list was checked and nothing new
  was found (see "Freshness").
- Saved to `<data>/amazon/order-pages.json` atomically, under the import lock, then the
  page is rebuilt. Report: `added`, `replaced`, `skipped_in_export`, `page`.
- Exit codes follow the existing table: 0, 2, 3 (no data folder, or no Amazon export
  yet), 4 (page couldn't be built; the saved file is kept and `build` can be rerun),
  20 (an import is running).

### Same shape as an exported order

G2 means a saved order must carry the same fields an exported Amazon order does, or the
page draws it differently. Exported Amazon orders have no `summary` (the page draws a
subtotal/tax line whenever one is present), so saved orders have none either. Item
`total` is unit × qty, and the order `total` is the page's grand total. When the export
later takes over, its own amounts replace these. Small differences in the meantime
(tax or rewards points that the export spreads over the items) are accepted.

### 3. Merging and the next export

- **Load:** `amazon.load()` reads `current/`, appends the saved orders whose IDs are
  not in the export, then merges `images.json` over both. `search`, `order`, `status`
  and the page see one list, and saved items get thumbnails like any other.
- **Images:** `update --amazon-images` and `gaps()` cover saved orders' ASINs too, so
  a saved order's image is looked up the same way an exported one's is.
- **Import:** after a successful swap, saved orders whose IDs are now in the export are
  removed from `order-pages.json`. The import report gains `saved_orders`:
  `{"replaced_by_export": [ids], "kept": n}`. A dry run reports the same without
  removing anything.
- `compare` and the "removed orders" count look at the export only, so saved orders never
  show up as orders the new export removed.

### 4. Freshness

- `order-pages.json` records `checked` (ISO date and time) for each `add` run that
  wasn't a dry run, including empty ones.
- `status` adds, for Amazon, `saved_orders` (count) and `checked`: the later of the
  last catch-up and the current export's import time.
- Skill rule (G4): before answering a question from Amazon data, if `checked` is more
  than 30 days old, mention once in the conversation that a refresh is available, and
  run it only if the user says yes.

## My calls (for review)

- **Storage is Amazon's:** `<data>/amazon/order-pages.json`, read inside the Amazon
  vendor module, not the core. That keeps the image merge in one place. The
  `add` command and import pruning are in the core, and only for vendors that declare
  they support saved orders (Amazon now). A later store opts in the same way.
- **No `summary`, grand total as the order total** (from G2; see "Same shape").
- **Known IDs come from `order-history order <id>`**, one call per candidate (at most
  30), instead of a new command.
- **File name** `order-pages.json`, matching `source: "order-page"`. The old outline's
  `--provisional` flag is dropped: `add` always saves this kind.
- **Shipment status maps to `status`:** not yet delivered → `In progress`, the same word
  exported in-flight orders show; delivered → empty (the normal state).
- **The seller name is not stored** (the order shape has no field for it, and nothing
  asks for it).
- **Stop rule:** 3 pages, then ask.
- **`checked` uses the import time** of the current export as its floor, so a fresh
  export counts as a refresh even with no catch-up run.

## Left to the builder

- How `checked` gets the export's import time (a marker file written by import, or the
  `current/` folder's time).
- Test fixture shapes and names; module placement of the add/merge code (`store.py` or a
  new module).
- The exact wording of the skill steps, within the flow above.

## Verification

- Unit tests with invented orders: add (new, replaced, skipped, empty list, each invalid
  input), load merge, import pruning and its dry run, `status` fields and the 30-day
  edge, exit codes, page rebuild with a saved order visible.
- Manual: one real catch-up with the user present, `add --dry-run` first, then a search
  that finds the new order. Private details stay out of the evidence.

## Proposed milestones

- **M7** `order-history add`, merging, images for saved orders, import pruning,
  `status` fields, tests.
- **M8** The Amazon skill flow (`vendors/amazon.md`, `SKILL.md` freshness rule), the
  amendments to `design.md` (its "no email source" non-goal now reads "dates only"), and
  the manual check with the user.
