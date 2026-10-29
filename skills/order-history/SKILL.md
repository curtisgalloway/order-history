---
name: order-history
description: Search and maintain the user's own purchase history from the order exports that stores let them download (Amazon's "Request My Data" zip, Adafruit's order-history CSV), through the order-history command-line tool. Use when the user asks when or where they bought something, what an order contained or cost, wants a store export imported ("import this") or a new Amazon export requested and downloaded, wants recent Amazon orders caught up from their order pages ("refresh my orders", "catch up"), wants the local order search page rebuilt, or wants missing item lists or product images filled in.
---

<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history

`order-history` keeps the user's purchase history from several stores in one local
**data folder** and answers questions about it. The user downloads each store's export
(the file a store lets you download with your own orders); you import it, report what
changed, and search it. The tool also writes a search page, `index.html` in the data
folder, which opens from disk with no server.

**Privacy.** Everything you read from this tool (search results, orders, import reports)
enters your context, so it is sent to the model provider like the rest of the
conversation. Fetch only what the question needs: prefer a narrow `search` over dumping
every order, and do not paste whole exports or caches. Never copy anything from the data
folder into a repository, an issue or a public document.

## Running it

Use the first that works:

1. `order-history` on `PATH` (installed with `uv tool install`). Check with
   `order-history --version`.
2. `python3 <skill-dir>/scripts/order-history`, where `<skill-dir>` is the folder that
   holds this SKILL.md. Needs Python 3.10 or later and nothing else. This is the normal
   case when the skill runs from a clone or a plugin, so a "command not found" from step 1
   is expected there.

If the data folder holds a `NOTES.md` (the user's notes about their exports: whose
account, when each was downloaded), read it before importing or answering questions about
coverage. Keep it out of anything you write elsewhere.

Below, `order-history` stands for whichever one works. Every command takes `--json` (one
JSON document on stdout; messages and progress go to stderr) and `--data-dir PATH`.
Prefer `--json` and read the document rather than the exit status alone (the one exception
is `--skill`, which always prints this file as Markdown). When a command fails before it
has a result to report (no data folder, bad usage, a file no store recognizes), stdout is
empty: read the exit code and the one-line reason on stderr instead. The command never
prompts, so it is safe to run unattended.

The store instructions are in `vendors/<store>.md` beside this file: what to download,
the export's columns and quirks, and how to read the raw files when the commands don't
answer a question. Read only the store you need. Without the files at hand,
`order-history skill amazon` (or `adafruit`) prints the same text, and
`order-history --skill` prints this document.

## First run

```bash
order-history status --json
```

Exit 3 with "run `order-history init`" means there is no data folder yet. Ask the user
where to keep their order data (the default is `~/Documents/Order History`), then:

```bash
order-history init                       # or: order-history init --data-dir PATH
```

Exit 3 with "can't read the data folder" means the folder exists but this process may not
list it. Never run `init` for this, and never report it as "nothing found". On macOS it is
almost always privacy protection on `~/Documents`: the app that started this session (a
terminal, an editor, an agent daemon) has not been granted that folder. Tell the user which
folder it is and that they grant access in System Settings > Privacy & Security, then
restart that app.

`init` creates the folder (mode 0700) and records it in
`~/.config/order-history/config.json`. The folder is chosen by, in order: `--data-dir`,
`$ORDER_HISTORY_DIR`, that config file, the default. Then ask the user to download an
export (see `vendors/<store>.md`) and import it.

For Amazon, when you can drive the user's own signed-in browser, you can also do the
requesting, waiting and downloading with them: `vendors/amazon.md`, "With a browser". The
user still signs in at each step, and you never type a credential. Between exports, the
same browser can catch up the newest orders from Amazon's order pages, when the user
asks (`vendors/amazon.md`, "Catching up from order pages").

## Importing an export

The user gives you a path: a zip, a CSV, or an already-unzipped folder. You don't need to
know which store it is from; the tool recognizes it by its contents.

1. Preview: `order-history import PATH --dry-run --json`. Nothing changes.
2. Tell the user what the report says (the fields are below), in a few lines: the store,
   the export's date and the current one's, orders and items before and after, how many
   were added and removed, and any findings. Removals and blanked titles deserve a
   sentence each, since a cumulative export should only grow.
3. If it looks right, run `order-history import PATH --json`. The previous export is moved
   to `<store>/archive/<its date>/` (never deleted), the new one becomes current, and the
   page is rebuilt. Report `archived_to` and `page`.

Exit 30 with `"action": "refused_older"` means the file is older than the current export.
Tell the user; import it with `--force` only if they say so. Exit 2 means no store (or
more than one) recognized the file: say which file, and check it is the export the vendor
file describes.

The report (`--json`) holds:

- `store`, `name`, `source` (the path given), `action` (`imported`, `dry_run` or
  `refused_older`), `as_of` (`old` and `new`: the newest order date in each export);
- `orders` and `items`: `before`, `after`, and the `added` and `removed` lists (order IDs;
  for items, `{order, asin, name}`);
- `findings`: store-specific lists. Amazon has `titles_renamed` and `titles_blanked`
  (`{order, asin, old, new}`): a newer export can blank a digital title, and the archived
  export is then the only copy of the old name;
- `archived_to`, `removed_staging` (folders left by an interrupted import, now removed),
  and `page` (the rebuilt page, or null);
- `saved_orders` (Amazon; null for other stores and for a refused import):
  `replaced_by_export` (IDs of saved orders the new export now has, which the import
  dropped, or would drop on a dry run) and `kept` (saved orders it still lacks). An
  `error` in it means dropping them failed; the import itself stands, the export's copy
  is the one shown, and the next import tries again.

## Saved orders: add

Orders placed after the export can be added from the store's own order pages (Amazon
only). The agent reads the pages and writes one JSON document; the tool never contacts
the store. The steps for reading Amazon's pages in the user's browser are in
`vendors/amazon.md`, "Catching up from order pages"; run them only when the user asks
(see "Is the data current?").

```json
{"store": "amazon",
 "orders": [{"id": "111-1234567-1234567", "date": "2026-03-03", "currency": "USD",
             "total": "28.14", "status": "In progress",
             "items": [{"name": "Example USB cable", "asin": "B000000000",
                        "qty": "2", "unit": "12.99"}]}]}
```

```bash
order-history add orders.json --dry-run --json   # report; saves nothing
order-history add orders.json --json             # or `add -` to read stdin
```

- An order needs `id` (Amazon's `111-1234567-1234567` form), `date` (YYYY-MM-DD) and at
  least one item with a `name`. It may have `currency` (default `USD`), `total` (the
  order's grand total), `status` and `site`; an item may have `asin`, `qty` (default 1),
  `unit`, `total` (default unit × qty) and `department`. Amounts are strings like
  `"12.99"` or numbers. Anything else, `summary` included, is refused: a saved order must
  look like an exported one, which has no subtotal/tax summary.
- An order whose ID is already in the export is skipped (the export wins); one already
  saved is replaced, for example after it shipped. An empty `orders` list is fine: it
  records that the pages were checked and nothing new was found.
- Saved orders show and search exactly like exported ones (`source` is `order-page`) and
  get product images like any other. They are kept in `<data>/amazon/order-pages.json`
  until an import brings an export that has them.
- The report has `store`, `dry_run`, `added`, `replaced` and `skipped_in_export` (order
  IDs), `saved_orders` (how many are saved now), `checked` and `page`.

## Answering questions

```bash
order-history search soldering iron --json        # every term must match
order-history search usb cable --store adafruit --kind physical --json
order-history order 111-1234567-1234567 --json    # one order; --store if the ID repeats
order-history status --json                       # what is imported, gaps, page time
```

`search` splits the query on spaces and keeps an item when every term is a substring
(ignoring case) of the item's fields (name, Amazon ASIN and department, Adafruit PID) or
its order's (store name, order ID, date, status, site, shipping method, and the word
`physical` or `digital`). So `cable` also finds "cables", and `2024-03` finds that month.
It returns orders, newest first, each holding only its matching items. Its document is
`{terms, empty, orders}`; `order`'s is `{id, empty, order}`. Exit 1 with `"empty": true`
means nothing matched, which is an answer, not an error: try fewer or other terms
(a brand, a shorter word) before telling the user there is no such purchase.

Substring matching also brings in noise: a short term matches inside unrelated words
(`air` in "pairs", `rework` in "fireworks"). Search with the most distinctive word of the
product first, read every result before answering, and confirm with a second term when
the first returns several unrelated orders.

An order has `store`, `id`, `date` (YYYY-MM-DD), `currency`, `source` (`export`, or
`order-page` for a saved order; see "Saved orders"),
`items`, and when present `total`, `status` (`In progress` for an order still in flight;
absent for the normal finished state), `digital`, `site`, `shipMethod`, `url` and
`summary`. Each item has `name` and `qty`, and when known `unit`, `total`, `url`, `asin`
or `pid`, `department` (Amazon's category) and `noImage` (true when the image lookup found
none). Empty fields are left out. An Adafruit order with an empty `items` list hasn't had
its item list fetched yet (see `update`). An order's `total` covers every item in it, not
only the matching ones. Returns and refunds are not in these results; for Amazon they are
in the export's own files (see `vendors/amazon.md`).

`status` prints `{data_dir, vendors, page_built, import_running}`. `vendors` lists each
store with `id`, `name`, `status` (`ok` or `missing`), and for an imported store `as_of`,
`orders`, `items` and `gaps` (`items_unfetched` for Adafruit, `images_missing` for
Amazon). Amazon also has `saved_orders` (how many of its orders are saved ones),
`checked` (date and time of the last refresh: the later of the last `add` and the
current export's import) and `stale` (true when `checked` is more than 30 days old).
`import_failed` on a store means an import couldn't
undo itself: tell the user and show them the file it names before doing anything else.

`order-history build` rebuilds the page from the current exports (import and update do it
themselves).

### Is the data current?

Before answering a question from Amazon data, look at the Amazon entry of
`order-history status --json`. When `stale` is true (more than 30 days since `checked`),
answer from what is there, and say once in the conversation that the data was last
refreshed on `checked`'s date and that you can catch up from the order pages if they
want. Don't repeat it later in the same conversation, and don't run the catch-up unless
the user says yes or asks for it themselves. Read `stale`; don't work out the age
yourself.

Even when `stale` is false, an order the user describes as recent that `search` can't
find may simply be newer than the data: say so and offer the catch-up, under the same
limit (once per conversation, counting the suggestion above, and only on a yes).

## Filling in what exports leave out: update

```bash
order-history update --dry-run --json      # how many lookups are missing; sends nothing
order-history update --json
```

- **Adafruit item lists** (on by default). Adafruit's export has no items; `update` looks
  each order up on Adafruit's guest order-status page. It needs the account email: from
  `--email`, `$ADAFRUIT_EMAIL`, or `<data>/adafruit/lookup_email.txt` (ask the user, and
  offer to save it in that file). It reads robots.txt first, waits at least 10 seconds
  between lookups, looks up only orders it hasn't already, and stops at the first sign of
  throttling. Don't try to speed it up or work around a stop.
- **Amazon product images** only with `--amazon-images`, and only when the user asks for
  them: it scrapes amazon.com product pages, which may be against Amazon's conditions of
  use. Say so when offering it.

With nothing missing it sends no request and exits 0, so it is safe to run on a schedule.
Each store's result has `requests`, `changed` (lookups saved), `pending` (still missing),
`failed`, `stopped` (`{reason, message}`: `throttled`, `robots`, `robots_unreadable` or
`unreachable`), `skipped` and `error`.

## Exit codes

Read the code together with the command: 20 and 21 mean "nothing done" and "partly done"
for every command, but what was partly done differs.

| Code | `search`, `order` | `import` | `update` | `add` | `build`, `init`, `status` |
| --- | --- | --- | --- | --- | --- |
| 0 | found | imported, or dry run | done, or nothing to do | saved, or dry run | done |
| 1 | nothing matched | — | — | — | — |
| 2 | bad usage; an unknown `--store`; an order ID found in several orders | bad usage; file not recognized, or claimed by two stores | bad usage | bad usage; an invalid input document (nothing saved); an unreadable `order-pages.json` | bad usage; unreadable config |
| 3 | no data folder, or it can't be read | no data folder, or it can't be read | no data folder, or it can't be read; or Adafruit orders need items and there is no lookup email | no data folder or it can't be read, or no export of that store yet | no data folder, or it can't be read (not `init`) |
| 4 | — | the page couldn't be built; the import was undone | the page couldn't be rebuilt; the caches are saved, run `build` | the page couldn't be rebuilt; the orders are saved, run `build` | `build`: no page shell, or the page couldn't be written; the old page is kept |
| 20 | — | nothing changed: another import is running, or a failure was rolled back; retry | nothing saved: throttled, robots.txt said no or couldn't be read, every lookup failed, or another update or an import is running; retry later | nothing saved: an import is running, or the file couldn't be written; retry | `build`: an import is running; retry |
| 21 | — | an import failed **and couldn't undo itself**: stop, show the user the folders named, change nothing | some lookups saved, then the run stopped; or the rebuild met a running import. Run `update` (or `build`) again later | — | — |
| 30 | — | older than the current export (pass `--force` only if the user says so), or an unsafe zip member or folder entry | — | — | — |

`--skill` and `skill` need no data folder; `skill <store>` exits 2 for an unknown store.

Exit 4 from a fresh install with no Node usually means the page shell (the search page
with no data in it, downloaded once per version from the project's GitHub release) could
not be fetched: offline, or no release exists for this version yet. An import that exits 4
is undone, so on a new machine nothing can be imported until a shell is found: tell the
user to go online, install a released version, or run the tool from a clone with Node and
npm installed (it then builds the shell itself). An existing data folder can still be
searched; only the page is stale.

## The data folder

```
<data>/
  index.html                  the search page (open it in a browser)
  NOTES.md                    the user's notes about their exports (optional)
  amazon/current/             the imported export, as unzipped
  amazon/archive/<date>/      earlier exports, kept
  amazon/images.json          product image cache (update --amazon-images)
  amazon/order-pages.json     saved orders (add), until an export has them
  adafruit/current/order_history.csv
  adafruit/archive/<date>/
  adafruit/items.json         item lists (update)
  adafruit/lookup_email.txt   account email for the lookups
```

Never edit `current/` by hand; import a new export instead. The tool never deletes an
archive.

## Migrating from an in-checkout layout

Before this tool, the exports lived inside a clone of its repository: Amazon's unzipped
folders (`Your Amazon Orders/`, `Your Returns & Refunds/`, `Additional Data/` and others)
at the checkout's top level, `Adafruit/order_history.csv`, `Adafruit/items.json`,
`Adafruit/lookup_email.txt`, `search/images.json`, `archive/` and `LOCAL.md`. To move
them into a data folder (`$C` is that checkout, `$D` the data folder; quote both, since
the paths have spaces):

1. Count each store's orders and items in the old build, to compare at the end. If
   `$C/search/app/src/generated/data.json` exists (the old page's data, written by the
   same build), count from it:

   ```bash
   python3 -c 'import json, sys, collections; d = json.load(open(sys.argv[1])); r = d["orders"]; print(d["generated"], dict(collections.Counter(x["store"] for x in r)), {s: sum(len(x["items"]) for x in r if x["store"] == s) for s in {x["store"] for x in r}})' "$C/search/app/src/generated/data.json"
   ```

   Otherwise use the counts `LOCAL.md` records for the last build.
2. `order-history init`, then confirm `$D` with `order-history status --json`. Start the
   notes now, so the counts are written down before anything moves:
   `cp "$C/LOCAL.md" "$D/NOTES.md"` (if there is one), then add the step 1 counts to
   `$D/NOTES.md`. They describe the account, so they go there and nowhere else.
3. Amazon: if the original zip is still around, `order-history import <zip>`. Otherwise
   gather the export's folders into one new folder outside the checkout first (importing a
   folder copies all of it, and the checkout also holds the code and `.git`):

   ```bash
   mkdir "$HOME/amazon-export"
   cp -R "$C/Your Amazon Orders" "$C/Your Returns & Refunds" "$C/Additional Data" "$HOME/amazon-export/"
   order-history import "$HOME/amazon-export" --json
   ```

   Copy every top-level folder the zip unpacked, not only these three; an archived copy
   under `$C/archive/` shows which folders an export had. Preview with `--dry-run` first,
   as for any import: its `after` counts should already match step 1.
4. Adafruit: `order-history import "$C/Adafruit/order_history.csv" --json`. Its report
   shows 0 items, since the item lists are in the cache copied next.
5. The caches keep their formats; copy them in:

   ```bash
   cp "$C/Adafruit/items.json" "$C/Adafruit/lookup_email.txt" "$D/adafruit/"
   cp "$C/search/images.json" "$D/amazon/"
   mkdir -p "$D/amazon/archive" "$D/adafruit/archive"
   cp -R "$C/archive/amazon-2026-01-31" "$D/amazon/archive/2026-01-31-from-checkout"
   ```

   Copy each `archive/<store>-<date>/` folder that way, into that store's `archive/`. Do
   not copy `LOCAL.md` over `NOTES.md` again here: step 2 already did, and the counts are
   in it now.
6. `order-history build`, then `order-history status --json`: the counts must match step 1.
   Add the result to `$D/NOTES.md`. Open `$D/index.html` and search for something the
   user knows they bought.
7. Only after the user has checked, and only with their go-ahead, delete the old copies:
   from the checkout, the export folders, `Adafruit/`, `search/` (the old page, its
   `images.json` and its generated `data.json`), `archive/` and `LOCAL.md`; and the
   gathered `$HOME/amazon-export`. Compare each with its copy in `$D` first (file counts
   or checksums). They are gitignored, so git won't show them as changes either way.
