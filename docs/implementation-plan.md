<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Agent-first order history — Implementation Plan

Design: [design](design.md), revision 2026-10-25 approved (commit `9633750`)
Notebook: [index](notebook/index.md); process log: [process log](process-log.md)

Project checks:

- Tests (from M1): `python3 -m unittest discover -s tests`
- Lint:
  - `uvx pylint==4.1.3 <py files>`, using Google's pylintrc at 88 columns, as CI
    sets it up. Locally, `~/.config/pylintrc` is the same file.
  - `uvx pyink --check <py files>`
- Page (from M3): `npm --prefix web ci && npm --prefix web run build`

## Conventions

**Branching.** `main` is protected: changes go through a pull request, and
`build` and `lint` are required checks until M3 changes them.

- Each milestone works on its own branch, `m<N>-<slug>`, made from an
  up-to-date `origin/main`.
- Pushing the branch, opening the pull request and merging each need the
  user's go-ahead (the user's push rule). The checkpoint commit happens
  locally first.
- Checkpoint commit prefix: `plan: M<N> — <title>`.

**Design gate:** approved 2026-10-25 (commit `9633750`).

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
| M2 | `import`: detect, stage, compare, archive, swap, rollback | M1 | pending |
| M3 | Node-free page; `search/` removed; CI and release workflow | M2 | pending |
| M4 | `update`: Adafruit items, opt-in Amazon images | M3 | pending |
| M5 | Skill, vendor docs, `--skill`, plugin manifest, packaging, docs | M4 | pending |
| M6 | Migrate real data, final verification, first release | M5 | pending |

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

**Design coverage:** R1 (registration), R3, R4

**Dependencies:** M1

**In scope:**

- `detect` and `install` for both vendors;
- `store.py` for staging, archiving, swapping and rolling back;
- the generic order and item comparison, plus Amazon's renamed and blanked
  digital titles;
- `import` with `--dry-run`, `--force` and `--json`;
- the zip-member safety check;
- the test-only vendor.

**Out of scope:** rebuilding the page after import (a no-op hook until M3).

### Implementation steps

1. `detect`:
   - Amazon: a zip or folder containing `Your Amazon Orders/Order History.csv`.
   - Adafruit: a CSV whose header matches the export's columns.

   Detection reads contents only.
2. `install` copies a folder, or extracts a zip into an empty staging folder.
   Before extracting, every member is checked: an absolute path, a `..`
   component or a symlink makes the import exit 30.
3. `store.import_export()` runs the design's import flow, steps 1–7.
   Rollback restores `current/` if a step from 5 on fails. A leftover
   `.staging-*` folder is cleaned up at the start of the next import and
   reported by `status`.
4. `compare(old, new)` gives orders and items added and removed, plus each
   vendor's own findings. Text output is a short summary; `--json` gives the
   full lists.
5. Register a test vendor inside a test to show R1: no core edits.

### Acceptance criteria

- [ ] Importing an Amazon fixture zip into an empty data folder installs it as
  `current/` and reports every order as added.
- [ ] Importing a newer fixture archives the old one to `archive/<as_of>/` and
  reports the exact differences, including a renamed digital title.
- [ ] `--dry-run` reports and leaves the folder byte-for-byte unchanged.
- [ ] An older export exits 30 without `--force`, and imports with it.
- [ ] A file no vendor claims, or that two claim, exits 2 and changes nothing.
- [ ] A zip with a `../x` member exits 30, and nothing is written outside staging.
- [ ] A failure injected after the archive step leaves the previous
  `current/` in place.
- [ ] Both vendors work from a zip, a CSV and a directory, wherever the vendor
  supports that format.

### Testing and review

- **Tests:** each criterion above, built from fixture zips made in `setUp`.
- **Review focus:** filesystem safety (the rename order, rollback, extracting
  zips), and that an import never deletes anything.

### Session sizing

Start from the design's "Import flow" section and M1's vendor modules. The
risk is in edge cases of the swap and rollback. Split point if it grows: land
detect and install with `--dry-run` first, then the swap.

### Evidence and findings

Status: pending. Evidence: [M2](evidence/M2.md). Notebook: [M2](notebook/M2.md).

## M3 — Node-free page and retiring `search/`

**Design coverage:** R7

**Dependencies:** M2

**In scope:**

- move `search/app` to `web/`, and read the data from
  `<script id="order-data">`;
- the data `format` number and the page's message when it doesn't match;
- `page.py` with the three-step shell lookup and atomic writes;
- rebuilding after import;
- delete `search/`;
- CI: a `page` job, and a release workflow that attaches `page-shell.html`;
- the required checks become `lint`, `test` and `page`.

**Out of scope:** `update` (M4).

### Implementation steps

1. Move the folder with `git mv search/app web`. Remove `json.stringify` and
   `generated/`. `main.tsx` parses the script element. The shell is built
   with that element empty.
2. `page.py`:
   - Look in the cache, then try a local build, then download from
     `https://github.com/<owner>/<repo>/releases/download/v<version>/page-shell.html`.
   - Escape `</` in the JSON before putting it in.
   - Write to a temporary file, then rename it into place.
   - Exit 4 when no shell can be found, and leave the existing page alone.
3. `import` calls `page.build()` after a successful swap.
4. Add `.github/workflows/release.yml`. On a pushed `v*` tag it builds the
   shell and uploads it to that release (`contents: write` for that job
   only). Actions are pinned to commit SHAs.
5. Change the required checks without blocking this milestone's own pull
   request. Branch protection requires `build`, which this pull request
   renames to `page`. Before merging, re-run `harden_repo.sh` with
   `lint test page`, with the user's go-ahead. Then confirm with
   `gh api …/protection`.
6. Delete `search/`, and update the `.gitignore` entries. Keep ignoring the
   old in-checkout data paths (R9).

### Acceptance criteria

- [ ] With `node` removed from `PATH` and a shell in the cache, `import`
  writes `<data>/index.html`, and the page shows the fixture orders.
  Checked in a browser.
- [ ] With the download stubbed, the shell is fetched once, cached, and used
  again.
- [ ] Offline, with no cache and no Node: exits 4, and the old page is unchanged.
- [ ] A page built with a mismatched `format` shows the mismatch message.
- [ ] Order data containing `</script>` doesn't break the page.
- [ ] CI's `page` job builds the shell and passes. The release workflow passes
  `actionlint`, or a manual review where that tool isn't available.
- [ ] `search/` is gone, and nothing refers to it.

### Testing and review

- **Tests:** the three shell sources; injection escaping; atomic writes;
  exit 4.
- **Manual:** open the built page and search the fixture data. Check the
  browser console for errors.
- **Review focus:** HTML injection safety; the release workflow's permissions
  and pinning; the branch-protection change order.

### Session sizing

Start from `web/` (the moved app), the design's "Page" section and the CI
files. The uncertainty is in the Vite build with an empty data element. Split
point if it grows: land `page.py` against a shell built locally first, then
the release workflow and the CI changes.

### Evidence and findings

Status: pending. Evidence: [M3](evidence/M3.md). Notebook: [M3](notebook/M3.md).

## M4 — Update

**Design coverage:** R6

**Dependencies:** M3

**In scope:**

- `enrich()` for Adafruit (from `fetch_adafruit_items.py`, keeping its
  politeness rules unchanged);
- `enrich()` for Amazon (from `fetch_images.py`), only with `--amazon-images`;
- `update`, with rebuilding, a progress log on stderr, `--json` and exit
  codes 20/21.

**Out of scope:** any download automation (phase 2).

### Implementation steps

1. Move the fetchers into the vendor modules. The network call becomes an
   injectable function, so tests can stub it.
2. `update` runs every vendor's enrichment and then rebuilds if anything
   changed. It does nothing, quickly, when nothing is missing.
3. Exit codes:
   - 20: robots.txt disallows the page, or throttling happened before any
     change.
   - 21: throttling happened after some orders were fetched (the cache
     stays partial).
   - 3: the lookup email is missing.
4. Read the lookup email from `<data>/adafruit/lookup_email.txt`, or
   `$ADAFRUIT_EMAIL`, or `--email`.

### Acceptance criteria

- [ ] With a stubbed fetch, `update` fills items for unfetched orders only,
  waits at least the configured delay between requests (the clock is
  stubbed), and rebuilds.
- [ ] A stubbed robots.txt that disallows the page exits 20 without fetching.
- [ ] A stubbed 429 midway exits 21 and keeps the orders already fetched.
- [ ] Without `--amazon-images`, no request goes to amazon.com (the stub
  asserts no calls).
- [ ] A second `update` with nothing missing makes no requests and exits 0.

### Testing and review

- **Tests:** each criterion above.
- **Review focus:** the politeness rules carried over exactly; no request at
  all without opt-in.

### Session sizing

Start from the two fetcher scripts and the M1 vendor modules. This is small;
no split expected.

### Evidence and findings

Status: pending. Evidence: [M4](evidence/M4.md). Notebook: [M4](notebook/M4.md).

## M5 — Skill, plugin, packaging and docs

**Design coverage:** R8, R9

**Dependencies:** M4

**In scope:**

- `SKILL.md`, `vendors/amazon.md` and `vendors/adafruit.md`;
- `--skill` and `skill`;
- `.claude-plugin/plugin.json`;
- `pyproject.toml` (for `uv tool install`);
- rewrites of the README, AGENTS.md and GLOSSARY.

### Implementation steps

1. Write `SKILL.md`, covering:
   - when to use the skill;
   - first run (`init`);
   - the import flow, including reporting the comparison to the user;
   - search, status and update;
   - the privacy note (search results go to the model provider);
   - migrating from an in-checkout layout.

   It points to `vendors/<id>.md` for each store's quirks and how to get its
   export. The export-format sections of AGENTS.md move into those files.
2. `--skill` prints `SKILL.md` through `importlib.resources`, with the version
   stamped in.
3. Write the plugin manifest. Check how plugins are discovered and validated
   in Claude Code's current documentation before writing it, rather than
   guessing.
4. Add `pyproject.toml` (`[tool.uv] package = true`, a script entry point,
   explicit packages).
5. Update the docs:
   - README: install as a plugin, with `uv tool`, or from the script path.
   - AGENTS.md: the developer guide for this repo, plus a pointer to the
     skill.
   - GLOSSARY: add vendor module, data folder, page shell, skill and plugin.

### Acceptance criteria

- [ ] `order-history --skill` prints exactly what `SKILL.md` contains, plus
  the version line. A test checks this.
- [ ] The plugin manifest passes the validator found in step 3, or a manual
  review against the documented schema if there is no validator.
- [ ] `uv tool install .` puts a working `order-history` on `PATH`.
- [ ] The docs mention no `search/` commands. The privacy note appears in both
  the README and SKILL.md.

### Testing and review

- **Tests:** the `--skill` equality test. Install in a temporary environment
  and run `order-history status`.
- **Review focus:** the skill is understandable on a cold start by an agent
  that has never seen this repo; it works under any agent (use the
  `agent-agnostic-skills` portability scan).

### Session sizing

This is mostly writing; it's small to medium. Split point if it grows: land
the skill and vendor docs first, then packaging and the plugin.

### Evidence and findings

Status: pending. Evidence: [M5](evidence/M5.md). Notebook: [M5](notebook/M5.md).

## M6 — Migration, final verification and first release

**Design coverage:** R10, R9, and a full-design check

**Dependencies:** M5

**In scope:**

- migrate this checkout's real data with the skill's documented steps;
- run the final system checks;
- tag `v0.1.0` (with the user's go-ahead) so the release has a page shell.

### Implementation steps

1. Before migrating, record each vendor's order and item counts from the
   current build in the data folder's `NOTES.md`, never in tracked files.
2. `init`. Then import the Amazon export folder and the Adafruit CSV, and
   move the caches, `archive/` and `LOCAL.md` (as `NOTES.md`) by the skill's
   steps.
3. Run the final system checks below.
4. With the user's go-ahead: tag `v0.1.0`, push the tag, and confirm the
   release has `page-shell.html`. Then clear the shell cache and rebuild with
   no Node, so the shell comes from the release download.

### Acceptance criteria

- [ ] `status` counts match the counts recorded before migration.
- [ ] The page opens from `<data>/index.html`, and a search for a known
  purchase finds it.
- [ ] The checkout no longer holds any export, cache or page. The leftover
  folders are deleted only with the user's go-ahead.
- [ ] A shell downloaded from the release builds the same page as a local build.
- [ ] A privacy grep of the whole repo is clean.

### Final system verification

- Importing a newer real export later (whenever one arrives) produces a
  sensible comparison report. This is recorded as a follow-up if no export
  is available yet.
- A cold-start check: a fresh agent session given only the skill finds a
  purchase and reports its date. Recorded in the evidence file.
- Every requirement R1–R10 is checked against its evidence in M1–M6.

### Evidence and findings

Status: pending. Evidence: [M6](evidence/M6.md). Notebook: [M6](notebook/M6.md).

## Discovered work / backlog

- Run `search_cases.json` against `web/src/search.ts` in the `page` job, using
  Node, so the two search implementations can't drift (a design risk). Small;
  can be added to M3 if there's room.
- `status` parses each export twice (`load`, then `as_of`). Harmless at today's sizes
  (M1 perf review); fold `as_of` into the loaded orders if it ever shows.
- The CLI has no equivalent of the page's Orders-view search (terms spread across an
  order's items). Add `search --orders` if an agent needs it.
- Phase 2: a download flow for each vendor, and `add --provisional` from order
  pages. Not planned yet.

## Next session

- **Current milestone:** M1 complete (checkpoint commit `plan: M1 — Package, data
  folder, and read-only commands` on branch `m1-package`). M2 is next.
- **Completed work:** design and plan merged to `main` in PR #2 (`a72b900`). M1 is
  committed locally on `m1-package`. Pushing it and opening and merging its pull request
  need the user's go-ahead.
- **Uncommitted state:** none for the milestone. `.no-pitch` (made by the user for a local
  pre-write hook) is gitignored and stays untracked.
- **Decisions pending:** none for M2.
- **Context boundary:** normal completion.
- **Resume action:** after M1 merges, create `m2-import` from an up-to-date `origin/main`
  and begin M2.
- **Read first:**
  - [design](design.md), "Import flow" and R3/R4;
  - this plan's M2 section;
  - [notebook index](notebook/index.md);
  - `skills/order-history/scripts/order_history/vendors/` and `cli.py`.
