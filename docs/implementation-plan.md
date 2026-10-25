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
| M2 | `import`: detect, stage, compare, archive, swap, rollback | M1 | complete |
| M3 | Node-free page; `search/` removed; CI and release workflow | M2 | complete |
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
- A downloaded shell is checked only for its structure, not a checksum (review F1). The
  user decides between pinning a SHA-256 in the package and turning on immutable releases.
- Until M6 tags a release, a machine without Node can't build the page; `__version__` must
  equal the tag's version (`release.yml` checks).
- No Adafruit item or Amazon image fetching until M4 (the scripts went with `search/`; port
  them from `15fb0ad:search/fetch_*.py`).

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

- Done in M3: `search_cases.json` runs against `web/src/search.ts` in the `page` job.
- The design's "Key decisions" says the tag ruleset stops a version's shell from being
  swapped; it doesn't cover release assets (M3 review F1). Correct the design when the user
  picks pinning or immutable releases.
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
- Add exit codes 20/21 (import busy or rolled back / rollback failed) to the design's
  exit-code table and the skill (M5).
- Exit 4 (no page shell, or the page couldn't be written) and `build` belong in the design's
  exit-code table and the skill (M5).
- The CLI has no equivalent of the page's Orders-view search (terms spread across an
  order's items). Add `search --orders` if an agent needs it.
- Phase 2: a download flow for each vendor, and `add --provisional` from order
  pages. Not planned yet.

## Next session

- **Current milestone:** M3 complete (checkpoint commit `plan: M3 — Node-free page and
  retiring search/` on branch `m3-page`). M4 is next.
- **Completed work:** M1 (PR #3) and M2 (PR #4) merged. M3 is committed locally on
  `m3-page`; pushing, the pull request and merging are the orchestrator's (with the user's
  go-ahead).
- **Gated before M3 merges:** re-run `harden_repo.sh` with `lint page "test (3.10)"
  "test (3.x)"` and confirm (exact commands in [M3 evidence](evidence/M3.md#branch-protection-plan-step-5-gated)),
  after the pull request's `page` job is green.
- **Uncommitted state:** none for the milestone. `.no-pitch` stays untracked.
- **Decisions pending:** shell integrity (M3 review F1): pin a SHA-256 of
  `page-shell.html` in the package, or turn on GitHub immutable releases (the release
  workflow already publishes draft-first so either works). Not blocking M4.
- **Context boundary:** normal completion.
- **Resume action:** after M3 merges, create `m4-update` from an up-to-date `origin/main`
  and begin M4. The fetchers are in git history: `git show 15fb0ad:search/fetch_adafruit_items.py`
  and `git show 15fb0ad:search/fetch_images.py`. `update` rebuilds through
  `cli._build_page()` (take `store.import_lock()` as `build` does).
- **Read first:**
  - [design](design.md), R6;
  - this plan's M4 section;
  - [notebook index](notebook/index.md);
  - the two fetchers (from history), `order_history/vendors/`, `order_history/page.py`.
