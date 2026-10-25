<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Agent-first order history — Design

Revision: 2026-10-25, draft for review

**Terms** (more in [GLOSSARY.md](../GLOSSARY.md)):

- **Export**: the file a store lets you download with your own order history
  (Amazon's "Request My Data" zip, Adafruit's order-history CSV).
- **Vendor module**: one store's code plus that store's agent instructions.
- **Skill**: a Markdown file of instructions an agent loads to learn a task.
  Claude Code, Codex and Antigravity all read the same format.
- **Plugin**: Claude Code's install unit, a folder of skills plus a manifest.
  Other agents use the skill folder directly.
- **Data folder**: where your exports, caches and the built page live. It is
  outside the code.
- **Page shell**: the search page built once with no data in it. Python fills
  in the data.

## Goal and non-goals

Make order history something an agent can keep up to date and search for
you, while the page you search in stays a single file that needs no server.

Outcomes:

- You download an export and tell your agent "import this". The agent
  identifies the store, archives the old export, installs the new one, tells
  you what changed, and rebuilds the page.
- An agent can answer "when did I buy that soldering iron?" from clean, normalized
  records rather than by hand-parsing CSVs.
- The page still opens straight from disk, and building it needs only Python.
- Adding a store means adding one vendor module, without editing core code.
- The repository never contains anyone's purchase data.

This design covers **phase 1: importing files you have already
downloaded.** Phase 2 adds, one vendor at a time, agent-driven flows for
requesting and downloading exports in your signed-in browser. Phase 2 is
outlined at the end so phase 1 leaves room for it, but it is not designed
here.

Non-goals:

- A server, a desktop app or a browser extension (see Key decisions).
- Unattended or scheduled imports. Getting a new export needs you: a login,
  an email confirmation, a click. A run is started by you, or by a schedule
  you set up for the steps that need no login.
- An MCP server. The command-line tool is the agent interface; an MCP server
  can wrap it later if some agent needs one.
- Reading order-confirmation emails. Amazon's no longer list full order
  details.

## Current behavior and constraints

Observed in the repository at `a329f8b`:

- `search/build.py` (316 lines) holds both stores' loaders (`load_amazon`,
  `load_adafruit`), the normalized shape (`new_order`, `new_item`), the
  `STORES` list, and the build. The build writes
  `search/app/src/generated/data.json`, runs `npm run build` (Vite with
  `vite-plugin-singlefile`, data inlined via `json.stringify`), and copies the
  result to `search/index.html`.
- `search/fetch_adafruit_items.py` fills `Adafruit/items.json` through
  Adafruit's guest order-status form. It reads robots.txt with its own
  User-Agent, waits at least 10 s plus jitter between requests, fetches only
  orders it doesn't have yet, and stops on 429/5xx. These rules carry over
  unchanged.
- `search/fetch_images.py` fills `search/images.json` (ASIN → image ID) by
  scraping amazon.com product pages. It is optional, because automated access
  may be against Amazon's conditions of use.
- Exports and caches sit inside the checkout, kept out of git by
  `.gitignore`: `Your Amazon Orders/`, `Adafruit/`, `archive/`, `LOCAL.md`.
- The page uses no browser storage and requests no data. The only network
  traffic is product thumbnails.
- CI (`.github/workflows/ci.yml`) builds from a clean checkout with no
  exports and runs pylint. `build` and `lint` are required checks on `main`.
- The Python is standard library only. Node 24 and npm are needed today to
  build the page.
- Importing has been done by hand. In this session that meant:
  - unzipping a new Amazon export;
  - moving the old one to `archive/amazon-<date>/`;
  - comparing the two, which found new item rows, renamed digital titles
    and titles blanked to `Not Applicable`;
  - rebuilding.

Assumptions:

- A1: Python 3.10+ is present wherever the agent runs. That holds on macOS and
  common Linux distributions; not verified on Windows.
- A2: Amazon's export arrives as one zip whose members include
  `Your Amazon Orders/Order History.csv`. Adafruit's arrives as one CSV with
  the header seen today. Detection relies on these.
- A3: Each new export is cumulative, so it replaces the previous one rather
  than adding to it. That's true for both stores so far.

## Requirements and acceptance criteria

- **R1 Vendor modules.** Each store is a Python module plus a Markdown
  instruction file. The core finds vendors through one registry list.
  Adding a store touches only the new files and that list.
  *Check:* a test vendor registered in a test passes import, load and
  search without core changes.
- **R2 Data folder setting.** The data folder is chosen by, in order:
  1. `--data-dir`
  2. `$ORDER_HISTORY_DIR`
  3. `data_dir` in `~/.config/order-history/config.json`
  4. the default, `~/Documents/Order History`

  `order-history init [--data-dir PATH]` creates the folder with mode 0700
  and records the choice. Any other command run before `init` exits 3 and
  names `init`.
  *Check:* tests for each level of the precedence, and for the missing-folder
  case.
- **R3 Import.** `order-history import PATH` accepts a zip, a CSV, or a
  directory (an already-unzipped export). It asks every vendor's `detect()`:
  - Exactly one vendor claims it: proceed.
  - None or several claim it: exit 2 with the reason, changing nothing.

  It then installs into a staging folder, loads both old and new, and
  compares them (R4). It refuses an export whose `as_of` date is older than
  the current one unless `--force`. Then it moves the current export to
  `<vendor>/archive/<as_of>/`, makes the staged one current, and rebuilds
  (R7).

  `--dry-run` prints the comparison and changes nothing. Zip members with
  absolute paths or `..` are refused. A failure part-way leaves the previous
  export current.
  *Check:* fixture tests for each of these branches, including a path
  traversal attempt in a zip.
- **R4 Comparison report.** Import reports, per vendor:
  - orders added and removed;
  - item rows added and removed;
  - vendor-specific findings, such as Amazon digital titles renamed or blanked
    to `Not Applicable`.

  It prints human-readable text, or a single JSON document with `--json`.
  *Check:* fixture with known differences → exact report.
- **R5 Search and lookup.**
  - `order-history search TERMS…` uses the page's matching rules:
    case-insensitive, every term must match, and the order's fields count
    toward each item.
  - `order-history order ID` prints one order.
  - `order-history status` prints, per vendor: the export's `as_of` date,
    order and item counts, enrichment gaps (unfetched Adafruit orders,
    missing images) and the page's build time.

  All three take `--json`. `search` exits 1 when nothing matches, and its JSON
  says `"empty": true`.
  *Check:* a shared case file (query → expected order IDs) run against the
  Python search, plus exit-status tests.
- **R6 Update.** `order-history update` runs each vendor's enrichment, then
  rebuilds.
  - Adafruit item fetching is on by default, with today's politeness rules.
  - Amazon image scraping runs only with `--amazon-images`.

  It is safe to run from a schedule: no prompts, nothing to do when nothing is
  missing, and exit codes from the 20s band when a site throttles.
  *Check:* tests with the fetch function stubbed. The politeness rules keep
  their current tests or gain them.
- **R7 Page without Node.** CI builds a data-free page shell from the Vite
  source, and the built shell is committed. Python writes
  `<data>/index.html` by putting the JSON into the shell's placeholder, and
  neither import nor update calls Node. CI fails if the committed shell
  differs from a fresh build of the source.
  *Check:* a test builds the page with no `node` on `PATH`. The CI staleness
  job fails on a deliberately stale shell.
- **R8 Skill and plugin.**
  - `SKILL.md` teaches the import, search and update flows, and points to one
    instruction file per vendor.
  - `order-history --skill` prints that same skill document, with the
    version stamped in.
  - A Claude Code plugin manifest wraps the skill folder.
  - The skill states that search results enter the agent's context, so they
    go to the model provider.

  *Check:* the manifest validates (exact check command to be discovered); a
  test confirms `--skill` output equals the shipped `SKILL.md`.
- **R9 Public safety.** Tests use made-up fixtures only. No path inside the
  checkout is a default data location, and `.gitignore` keeps covering the
  old in-checkout paths.
  *Check:* grep the repo for the data folder's contents; review fixtures by
  hand.
- **R10 Migration.** The existing in-checkout data can be moved to the data
  folder:
  - The exports go through `import` (the Amazon export as a directory).
  - The caches (`items.json`, `images.json`), `archive/` and `LOCAL.md` (which
    becomes `NOTES.md`) move by documented commands in the skill.

  *Check:* after migrating a checkout's data, `status` shows the same order
  and item counts per vendor as that checkout's last build. The counts are
  recorded in the data folder's `NOTES.md`, never in tracked files.

## Architecture and behavior

### Layout (proposed)

```
.claude-plugin/plugin.json             Claude Code plugin manifest
skills/order-history/
  SKILL.md                             agent entry point (also emitted by --skill)
  vendors/amazon.md, adafruit.md       per-vendor instructions, read on demand
  scripts/order-history                executable entry point
  scripts/order_history/
    cli.py                             argparse subcommands, exit codes, --json
    config.py                          data-folder resolution (R2)
    model.py                           new_order/new_item, money(), compaction
    store.py                           staging, archive, atomic swap (R3)
    search.py                          match rules shared with the page (R5)
    page.py                            shell + data → index.html (R7)
    page/shell.html                    built by CI, committed
    vendors/__init__.py                VENDORS registry
    vendors/amazon.py, adafruit.py
web/                                   Vite + React source (moved from search/app)
tests/                                 unittest, made-up fixtures only
```

`search/` and its scripts go away. `pyproject.toml` lets the tool be
installed with `uv tool install`, which puts `order-history` on `PATH`. The
skill uses the script path when it isn't installed.

### Vendor interface

```python
class Vendor(Protocol):
    ID: str                      # "amazon"; also the data subfolder name
    NAME: str                    # "Amazon"
    def detect(path) -> bool     # inspects contents, never the filename
    def install(src, dest)       # unpack/copy an export into an empty folder
    def as_of(folder) -> date    # newest order date in the export
    def load(vendor_dir) -> list[Order]
    def compare(old, new) -> dict  # vendor-specific findings for R4
    def enrich(vendor_dir, opts) -> EnrichResult  # optional (R6)
```

The current loaders and fetchers move in mostly unchanged. The core owns
staging, archiving, swapping, the generic order and item comparison, search,
and the page.

### Data folder

```
<data>/
  NOTES.md                 your notes about these exports (was LOCAL.md)
  index.html  data.json    built page and its data
  amazon/current/          the installed export
  amazon/archive/<as_of>/  earlier exports, never deleted by the tool
  amazon/images.json       image cache
  adafruit/current/order_history.csv
  adafruit/archive/<as_of>/
  adafruit/items.json      item cache
  adafruit/lookup_email.txt
```

### Import flow

1. Each vendor's `detect()` is called. Exactly one must claim the file.
2. `install` copies it into `<vendor>/.staging-<timestamp>/`.
3. `load` runs on both the staged export and `current/`, and `compare`
   produces the report.
4. With `--dry-run`, or when the export is older than the current one without
   `--force`: print the report, delete the staging folder, and stop.
5. `current/` is renamed to `archive/<old as_of>/`. If that folder already
   exists, the time is added to the name.
6. The staging folder is renamed to `current/`.
7. The data is rebuilt and the page written to a temporary file, then renamed
   into place.

If a step from 5 on fails, the folders are put back as they were. A
leftover `.staging-*` folder is reported by `status` and removed by the next
import.

### Page

`web/` keeps today's React page, with one change: instead of importing
`generated/data.json`, it reads the data from
`<script id="order-data" type="application/json">` in the page. Vite builds the
shell with that script element left empty. `page.py` escapes `</` in the JSON
and fills it in. This removes `json.stringify`, the generated folder and the
TypeScript-inferred data type.

### Exit codes

The codes follow the house CLI conventions:

| Code | Meaning |
| --- | --- |
| 0 | ok |
| 1 | search found nothing |
| 2 | bad usage, or an unrecognized or ambiguous file |
| 3 | no data folder, or no export for a vendor |
| 20/21 | a site throttled before or during an update |
| 30 | an older export without `--force`, or a zip-member path refused |

## Key decisions

- **An agent plus a command-line tool, not a server.** Considered: a
  localhost server with Update buttons; a server kept running by launchd; a
  browser extension; a browser-only page; a hosted page talking to a local
  helper. The browser blocks a page from reading Adafruit's and Amazon's
  responses (probed 2026-10-25: neither sends the headers, called CORS, that
  would allow it). So in-page fetching needs a server or an extension, and an
  extension means rewriting the Python in TypeScript. Agents already handle
  the judgment work in imports. The cost is that updating happens in the
  agent, not in the page.
- **One Python module plus one Markdown file per vendor.** It keeps each
  store's code and instructions together, and loads only the relevant store's
  notes into the agent.
- **Commit the built page shell.** The alternative was downloading it from a
  release on first run, which needs the network and adds a release step to
  every change. Committing it costs a large generated file in diffs; CI's
  staleness check keeps it honest.
- **The data folder is a setting, defaulting to `~/Documents/Order History`.**
  Chosen by the user.
- **The Node-free page is in phase 1.** Chosen by the user. Without it, a
  plugin user needs Node to see the page.
- **No email source.** Amazon's confirmation emails lack full details.

## Cross-cutting concerns

- **Privacy:**
  - The data folder is created 0700.
  - The page never makes data requests.
  - Agent searches do send matching orders to the model provider. The skill
    and the README say so.
- **Untrusted input:** exports are downloads. The zip reader refuses unsafe
  member paths and doesn't execute anything. CSV parsing is standard library
  only.
- **Politeness:** the Adafruit rules are kept exactly; the image scraper stays
  opt-in.
- **Compatibility:** `.gitignore` keeps covering the old in-checkout paths, so
  a checkout that still has data in it doesn't leak it. The old `search/`
  commands are removed, not kept as wrappers.
- **Performance:** about 6k items load and search in well under a second in
  Python. The built page stays about the size it is today, around 2 MB.

## Verification strategy

- Unit tests (`python3 -m unittest`, standard library) cover config
  precedence, detection, install, comparison, the swap and its rollback,
  search cases, exit codes and page injection. They use made-up fixtures in
  `tests/fixtures/`: a tiny Amazon zip and an Adafruit CSV.
- CI gets three jobs:
  - `lint`: as today, extended to `skills/` and `tests/`.
  - `test`: the unit tests on Python 3.10 and the latest version.
  - `page`: builds the shell and fails if the committed copy differs.

  The required checks become `lint`, `test` and `page`. The build job is
  replaced, so the hardening script is re-run with the new check names.
- Manual check: migrate this checkout's real data (R10), compare `status`
  counts with the current build, open the page and search for a known purchase.
- The plugin manifest is checked with Claude Code's validator. The exact
  command is to be discovered.

## Risks and open questions

- **The search rules could drift** between `search.ts` and `search.py`. The
  shared case file guards the Python side only. A small Node test in the
  `page` job could run the same cases against `search.ts`, which is cheap
  since Node is already present there. Proposed; to be decided in the plan.
- **Amazon's zip layout or Adafruit's columns may change** (A2). Detection
  then exits 2 with a clear message rather than misreading the file. Fixing it
  is a vendor-module change.
- **Plugin distribution:** install from the repo URL, or through a
  marketplace listing? This doesn't block phase 1. Recorded for the README.
- **Windows** is unverified (A1). Not a goal.

## Phase 2 outline (not designed here)

- Each vendor's `.md` gains a download flow: the steps for the agent's
  browser tool to request or download the export in your signed-in session.
  It asks before every submit and download, and never enters passwords or
  solves captchas.
- Optional catching up between exports. The agent reads your order pages and
  passes records to `order-history add --provisional`. Those records carry
  `source: "order-page"` and are replaced when an export includes the same
  order ID. Phase 1 reserves the `source` field in the order shape so this
  needs no migration.
