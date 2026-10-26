<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Agent-first order history — Implementation Plan

Design: [design](design.md), revision 2026-10-25 approved (commit `9633750`); M7–M8:
[catching up from order pages](design-order-pages.md), revision 2026-10-25 approved
Notebook: [index](notebook/index.md); process log: [process log](process-log.md)

Project checks:

- Tests (from M1): `python3 -m unittest discover -s tests`
- Lint:
  - `uvx pylint==4.1.3 <py files>`, using Google's pylintrc at 88 columns, as CI
    sets it up. Locally, `~/.config/pylintrc` is the same file.
  - `uvx pyink --check <py files>`
- Page (from M3): `npm --prefix web ci && npm --prefix web run build`

## Conventions

**Branching.** `main` is protected: changes go through a pull request. Required
checks: `build` and `lint` until M3; from M3's merge, `lint`, `page`,
`test (3.10)` and `test (3.x)` (GitHub reports a matrix job per leg, so a bare
`test` context would never report).

- Each milestone works on its own branch, `m<N>-<slug>`, made from an
  up-to-date `origin/main`.
- Pushing the branch, opening the pull request and merging each need the
  user's go-ahead (the user's push rule). The checkpoint commit happens
  locally first.
- Checkpoint commit prefix: `plan: M<N> — <title>`.

**Design gate:** approved 2026-10-25 (commit `9633750`). Catching up from order pages
(M7–M8): approved by the user 2026-10-25 ("approved").

**User overrides:** none.

**Review:**

- Method: the `review-swarm` skill, run once per milestone at the close with
  `--close`, letting its planner choose the tier.
- If it's unavailable, a reviewer subagent with fresh context.
- Fixes are confirmed by the swarm's recheck, not by a second review.
- Review and fixes come before the checkpoint commit, which is the last step.

**Privacy:** test fixtures are invented. Before every commit, grep the staged
diff for addresses, home paths, real order IDs, product names and account
counts (AGENTS.md, "Before committing").

**During the transition:** `search/` keeps working until M3 removes it, so
`main` always has a working page.

## Status

| ID | Outcome | Dependencies | Status |
|----|---------|--------------|--------|
| M1 | Package, data folder, vendors load; `init`/`status`/`search`/`order` | — | complete |
| M2 | `import`: detect, stage, compare, archive, swap, rollback | M1 | complete |
| M3 | Node-free page; `search/` removed; CI and release workflow | M2 | complete |
| M4 | `update`: Adafruit items, opt-in Amazon images | M3 | complete |
| M5 | Skill, vendor docs, `--skill`, plugin manifest, packaging, docs | M4 | complete |
| M6 | Migrate real data, final verification, first release | M5 | complete |
| M7 | `add`: saved orders from order pages, merged, pruned by import | M6 | complete |
| M8 | Amazon catch-up flow in the skill; one real run with the user | M7 | pending |

## Design coverage

| Requirement | Milestones | Verification |
|-------------|------------|--------------|
| R1 vendor modules | M1, M2 | test vendor registered in a test only |
| R2 data folder setting | M1 | precedence tests; missing folder exits 3 |
| R3 import | M2 | fixture tests per branch, zip traversal |
| R4 comparison report | M2 | exact report on a fixture pair |
| R5 search and lookup | M1 | shared case file; exit 1 with `"empty": true` |
| R6 update | M4 | stubbed fetch tests; throttle exit codes |
| R7 page without Node | M3 | cached shell with no node on PATH; stubbed download; offline exits 4 |
| R8 skill and plugin | M5 | `--skill` equals SKILL.md; manifest check |
| R9 public safety | every milestone, M6 | staged-diff grep; fixture review |
| R10 migration | M6 | `status` counts equal the last build's (kept in NOTES.md) |
| G1 orders from order pages | M7, M8 | `add` tests; one real catch-up (M8) |
| G2 saved orders look the same | M7 | shape tests (no `summary`, item totals, images); page built with a saved order |
| G3 the next export takes over | M7 | import pruning tests, dry run included; `removed` ignores saved orders |
| G4 only when asked; 30-day suggestion | M7, M8 | `status` `checked` tests at the 30-day edge; skill text |

## M1 — Package, data folder, and read-only commands

**Outcome:** the `order-history` package under `skills/order-history/scripts/`, with
`init`, `status`, `search` and `order` (text and `--json`, exit codes 0/1/2/3), both
vendor loaders reading `<data>/<vendor>/current/`, invented fixtures, 59 unit tests, and
a CI `test` job (Python 3.10 and latest, not yet required).

**Design coverage:** R1 (load path), R2, R5, R9. **Dependencies:** none.

### Evidence and findings

Status: complete. Evidence: [M1](evidence/M1.md) (full milestone definition, checks and
review). Notebook: [M1](notebook/M1.md).

Open limitations:

- The test comparing the new loaders with `search/build.py` runs only on Python 3.12+,
  because `build.py` itself needs 3.12. It goes away with `search/` in M3.
- `search` uses the page's Items-view rule (all terms on one item plus its order). The
  page's Orders view (terms spread across an order's items) has no CLI equivalent.

## M2 — Import

**Outcome:** `order-history import PATH [--dry-run] [--force] [--json]` for both vendors
(Amazon from a zip or folder, Adafruit from its CSV): detection, staging, the comparison
report (orders and items added and removed; Amazon titles renamed and blanked), archiving
to `archive/<as_of>/`, the swap with rollback, zip and folder safety checks, an import
lock, and a failed-rollback note that stops later imports. 98 unit tests.

**Design coverage:** R1 (registration), R3, R4. **Dependencies:** M1.

### Evidence and findings

Status: complete. Evidence: [M2](evidence/M2.md) (full milestone definition, checks and
review). Notebook: [M2](notebook/M2.md).

Open limitations:

- The rebuild after import is a no-op hook (`rebuild=`) until M3 plugs in `page.build()`.
- Adafruit reports always show 0 items: its export has no item lines (M4 fills
  `items.json`).
- Exit codes 20 and 21 gained import meanings (see the evidence file); the design's
  exit-code table should list them when M5 rewrites the docs.

## M3 — Node-free page and retiring `search/`

**Outcome:** the page shell (`web/`, moved from `search/app`) reads its data from
`<script id="order-data">` and shows a message on a `format` mismatch; `page.py` gets a
shell from the cache, a local npm build or the release download, escapes every `<`, and
writes `<data>/index.html` atomically (exit 4 with none); `import` rebuilds, and a new
`build` command rebuilds by hand under the import lock. `search/` is deleted. CI has a
`page` job (including `search_cases.json` against `search.ts` under Node), and
`release.yml` attaches `page-shell.html` to a `v*` tag's release. 122 unit tests.

**Design coverage:** R7, R9 (`.gitignore`). **Dependencies:** M2.

### Evidence and findings

Status: complete. Evidence: [M3](evidence/M3.md) (full milestone definition, checks and
review). Notebook: [M3](notebook/M3.md).

Open limitations:

- Branch protection still requires `build`: the change to `lint`, `page`, `test (3.10)`,
  `test (3.x)` is gated on the user (command in the evidence file) and must run before
  this milestone's pull request merges.
- The browser check ran over a loopback HTTP server; the browser tool refuses `file://`.
  Opening `<data>/index.html` from disk once by hand is open.
- A downloaded shell is checked only for its structure, not a checksum (review F1).
  Resolved 2026-10-25 by user decision: immutable releases are on; no SHA pin.
- Until M6 tags a release, a machine without Node can't build the page; `__version__` must
  equal the tag's version (`release.yml` checks).
- No Adafruit item or Amazon image fetching until M4 (the scripts went with `search/`; port
  them from `15fb0ad:search/fetch_*.py`).

## M4 — Update

**Outcome:** `order-history update [--email E] [--amazon-images] [--dry-run] [--json]`:
Adafruit item lists from the guest order-status page (on by default) and, only with
`--amazon-images`, Amazon product images, both ported from the M3-deleted fetchers with
their politeness rules (plus stopping on more transient errors), then a rebuild when a
cache changed. Exports are read under the import lock, lookups run under a separate update
lock. Exit codes 0, 3 (no lookup email), 4, 20, 21. Network, clock and jitter are injected;
no test or manual run reached either store. 156 unit tests.

**Design coverage:** R6. **Dependencies:** M3.

### Evidence and findings

Status: complete. Evidence: [M4](evidence/M4.md) (full milestone definition, checks and
review). Notebook: [M4](notebook/M4.md).

Open limitations:

- Never run against the real sites (by design, this milestone sends no real request). The
  first real `update` is M6's, on the migrated data.
- An Adafruit order whose lookup fails for good (a 404, or a page that isn't its status
  page) is retried on every run and keeps `update` at exit 20/21. Not cached as a failure,
  as before.
- `update` exit 21 means "partly done; run again later", import's 21 "rollback failed;
  check the folders": the same band, read with the command (review F5). M5's skill must say
  so.

## M5 — Skill, plugin, packaging and docs

**Outcome:** `skills/order-history/SKILL.md` (first run, import and what to report, search,
status, update, privacy, a per-command exit-code table, migrating from an in-checkout
layout) and `vendors/amazon.md`, `vendors/adafruit.md` (the export formats and every gotcha
moved out of AGENTS.md); `--skill` and `skill [STORE] [--json]` printing them through
`importlib.resources` (the package holds symbolic links to them; the wheel holds files);
`.claude-plugin/plugin.json` and a one-plugin `marketplace.json`, both passing `claude plugin
validate --strict`; `pyproject.toml` for `uv tool install`; README, AGENTS.md (now the
developer guide) and GLOSSARY rewritten. 173 unit tests.

**Design coverage:** R8, R9. **Dependencies:** M4.

### Evidence and findings

Status: complete. Evidence: [M5](evidence/M5.md) (full milestone definition, checks and
review). Notebook: [M5](notebook/M5.md).

Open limitations:

- The plugin is validated but was never loaded into a Claude Code session; the install line
  works only once this is on `main`.
- Before tagging `v0.1.0` (M6), `__version__` and `plugin.json`'s `version` both become
  `0.1.0` (a test keeps them equal; `release.yml` checks the tag against `__version__`).
- `marketplace.json` settles the design's open "repo URL or marketplace listing" question
  as "the repo is its own marketplace" (notebook decision); a listing elsewhere stays open.

## M6 — Migration, final verification and first release

**Outcome:** the real in-checkout data migrated into the data folder by SKILL.md's own steps,
with `status` counts equal to the last in-checkout build's (kept in `<data>/NOTES.md`);
SKILL.md corrected where migrating and a cold-start check showed it wrong; version `0.1.0`;
release `v0.1.0` published (immutable, with `page-shell.html`), whose shell is byte-identical
to a local build; the old checkout's exports, caches and page deleted after a SHA-256 check;
the page checked from `file://` by the user; R1–R10 checked against evidence.

**Design coverage:** R10, R9, and the full-design check. **Dependencies:** M5.

### Evidence and findings

Status: complete. Evidence: [M6](evidence/M6.md) (full milestone definition, checks, review,
release and close-out self-check). Notebook: [M6](notebook/M6.md).

Open limitations:

- The "newer real export gives a sensible comparison report" check waits for the next
  export (backlog).
- The browser tool can't open `file://`; the page's from-disk check was the user's.

## M7 — Saved orders: `add`, merging, pruning

**Outcome:** `order-history add FILE|- [--dry-run] [--json]` saves orders read from Amazon's
order pages to `<data>/amazon/order-pages.json` (atomically, under the import lock; a new
core module `saved.py`) and rebuilds the page; `amazon.load()` shows the saved orders the
export lacks, with images, and `update --amazon-images` covers their ASINs; import drops
the saved orders a new export has and reports `saved_orders`; `status` gains
`saved_orders`, `checked` and `stale`. 214 unit tests.

**Design coverage:** G1 (storage), G2, G3, G4 (`checked`). **Dependencies:** M6.

### Evidence and findings

Status: complete. Evidence: [M7](evidence/M7.md) (full milestone definition, checks and
review). Notebook: [M7](notebook/M7.md).

Open limitations:

- No real catch-up has run; the flow and the run with the user are M8.
- `checked`'s import time is `current/`'s mtime, which a copy or restore of the data folder
  can reset.
- M8's skill rule should read `status`'s `stale` (more than 30 days since `checked`)
  rather than compute dates.

## M8 — The Amazon catch-up flow

**Outcome:** `vendors/amazon.md` gains "Catching up from order pages": status first; the
order list read newest first until a known ID (checked with `order-history order <id>`),
at most 3 pages before asking; each new order's details page read by its
`data-component` hooks (quantity from the image badge, absent means 1; shipment status
to `In progress` or empty; grand total as the order total); then `add --dry-run`,
report, `add`. Stop at any sign-in prompt; never type a credential. SKILL.md gains the
rule: only when asked, and when answering from Amazon data whose `checked` is over 30
days old, suggest a refresh once per conversation. `design.md`'s "no email source"
non-goal and phase 2 outline point to the new design.

**Design coverage:** G1 (flow), G4 (rule). **Dependencies:** M7.

**Scope:** documentation and one manual run. Excluded: digital orders, older-order
status changes, other stores, unattended runs.

**Acceptance criteria:**

- One real catch-up with the user present finds the orders newer than the export,
  `add --dry-run` reports them, and after `add` a search finds a new order.
- No order ID, product name, date or count from the real run appears in a tracked file
  (the evidence describes the run in generic terms).
- `tests/test_skill.py` passes (the skill and vendor docs are still emitted).

**Verification:** the project checks; the manual run recorded in `docs/evidence/M8.md`.

**Review:** `review-swarm --close` (it will likely pick the light tier for a docs
change). Focus: the steps match what the pages showed, and no credential or captcha
step is left to the agent.

**Sizing and checkpoint:** small; the manual run depends on the user being available.
If they aren't, land the docs and leave the run as the open item.

**Status:** pending.

## Discovered work / backlog

- Done in M3: `search_cases.json` runs against `web/src/search.ts` in the `page` job.
- Done in M4: the design's "Key decisions" now credits immutable releases (turned on by the
  user's decision, 2026-10-25), not the tag ruleset, with protecting release assets (M3
  review F1). No SHA-256 pin.
- The design's data-folder layout lists `data.json`; M3 doesn't write it (nothing reads it).
  Drop it from the design at the next revision.
- UI development lost live data: `npm run dev` shows the "no order data" message. If it's
  missed, let the dev server read a built page's data.
- `status` parses each export twice (`load`, then `as_of`), and so does `import` for each
  side (`read`, then `as_of`; M2 review F10). Harmless at today's sizes; fold `as_of` into
  the loaded orders if it ever shows.
- R10 / M6: importing a folder copies the whole folder, and the in-checkout Amazon export
  sits at the checkout root beside the code, `.git` and `archive/`. M6's migration steps
  must gather the export folders into their own folder first (or import the original
  zip). Found in M2.
- Zip extraction has no cap on total size or member count (M2 review F2, declined for
  now). If a cap is wanted, set it from a real export's size, since Amazon's run to
  gigabytes with photos and invoices.
- Done in M5: exit codes 20/21 per command, 3 and 4 in the design's table and the skill's
  per-command table (M4 review F5).
- `update` has no `--limit`, `--delay` or `--refresh` (the old scripts had them). Add
  `--limit` if a first full Amazon image run (thousands of pages at about 2 s each) needs
  to be spread out; never let `--delay` go below the 10 s Adafruit floor. Found in M4.
- An Adafruit order whose lookup always fails is asked again on every `update`. If that
  shows up in real use, cache the failure with a date and retry it only after a while.
  Found in M4.
- The CLI has no equivalent of the page's Orders-view search (terms spread across an
  order's items). Add `search --orders` if an agent needs it.
- From the plugin cache (a full copy of the repository, `web/` included) `page.py` takes the
  development path whenever `npm` is on `PATH`, running `npm ci` and a build inside the
  plugin's cached copy instead of downloading the shell. Consider requiring a `.git` beside
  `web/`, or an opt-in variable, for the local build. Found in M5.
- `claude plugin validate` reports `ICON_MISSING` (non-blocking); add a 512–2048 px PNG
  only if the plugin is submitted to Anthropic's directory. Found in M5.
- `search`'s substring rule makes short terms match inside unrelated words (`air` in
  "pairs"); the skill now says to read every result. If agents keep tripping on it, add a
  whole-word option or rank results. Found in M6's cold start.
- Importing a newer real export (the final-verification check that its comparison report
  is sensible) waits for the next Amazon or Adafruit export. Found in M6.
- Phase 2: the Amazon download flow is done (PR #10). Catching up from order pages is
  M7–M8 ([design](design-order-pages.md)); the old outline's `--provisional` flag is
  dropped. A download flow for Adafruit is not planned.

## Next session

- **Current milestone:** M8 (pending).
- **Completed work:** M1–M6 (PRs #3–#9); the Amazon browser export flow (PR #10); M7 on
  branch `m7-saved-orders` (checkpoint commit `plan: M7 — Saved orders: add, merging,
  pruning`; push and PR are the orchestrator's).
- **Uncommitted state:** none. `.no-pitch` stays untracked.
- **Decisions pending:** none.
- **Context boundary:** normal.
- **Resume action:** start M8 on `m8-<slug>` from an up-to-date `origin/main` once M7 is
  merged.
- **Read first:** [catching up from order pages](design-order-pages.md), M8 above,
  `skills/order-history/vendors/amazon.md`, SKILL.md "Saved orders: add" and the `status`
  fields, [M7 evidence](evidence/M7.md) limitations.
