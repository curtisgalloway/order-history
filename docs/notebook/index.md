<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Notebook index

Updated: 2026-10-25T16:21-0700

A row is stale when its chapter has an entry newer than "indexed through".

## Chapters

### [design — Agent-first restructure](design.md)
Entries: 2026-10-25T12:21-0700 through 2026-10-25T13:29-0700
Outcome: design approved; implementation plan M1–M6 written
- Neither store sends CORS headers, so a page can't fetch from them.
- Dead ends: localhost server, extension, hosted helper, scheduled imports, email receipts.
- Chosen: agent + stdlib CLI + static page; one module per vendor; data folder outside the repo.
- Page shell is a release asset, never committed (user direction).

### [M1 — Package, data folder, and read-only commands](M1.md)
Entries: 2026-10-25T13:56-0700 through 2026-10-25T14:10-0700
Outcome: complete; `init`/`status`/`search`/`order` with tests and a CI `test` job
- `search.py` uses the page's Items-view rule; the Orders view has no CLI equivalent.
- `search/build.py` needs Python 3.12 (nested f-string quotes); `model.money` was rewritten for 3.10.
- A pitch-gate hook blocked the first session; resolved with a user-made, gitignored `.no-pitch`.
- Review: 8 findings (1 medium), all fixed; text output now replaces control characters.

### [M2 — Import](M2.md)
Entries: 2026-10-25T14:15-0700 through 2026-10-25T14:30-0700
Outcome: complete; `import` with staging, comparison, archive, swap, rollback, safety checks
- Vendors gained `read(folder)` (export only); comparisons never see the caches.
- Review F1: an archive name from an unchecked export date could move `current/` outside the data folder; only `YYYY-MM-DD` names it now.
- A failed rollback writes `<vendor>/IMPORT-FAILED.txt` and blocks that store's imports (exit 21).
- Folder imports copy the whole folder; M6 migration must gather the export first (backlog).

### [M3 — Node-free page and retiring `search/`](M3.md)
Entries: 2026-10-25T14:35-0700 through 2026-10-25T14:53-0700
Outcome: complete; page shell + `page.py` (cache, local build, release download), `build`, `search/` deleted, `page` CI job, `release.yml`
- Required checks are job names: the matrix `test` reports as `test (3.10)` and `test (3.x)`.
- Every `<` in the data is escaped as `\u003c`; `FORMAT` and `DATA_FORMAT` are kept equal by a test.
- Browser tool refuses `file://`; checked over a loopback server instead.
- Review F1: the tag ruleset doesn't protect release assets; shell integrity is the user's call.

### [M4 — Update](M4.md)
Entries: 2026-10-25T15:01-0700 through 2026-10-25T15:21-0700
Outcome: complete; `update` (Adafruit items; Amazon images only with `--amazon-images`), network/clock injected
- Politeness carried over; port also stops on 403/5xx/network errors instead of caching "no image" (review F1, R1).
- Exports read under the import lock, lookups under a separate `.update.lock` (review F3).
- Exit 20/21 keep M2's band meanings; 3 (no email) wins over them; F5 (21 shared with import) declined.
- M3 F1 resolved: immutable releases on by user decision; design corrected.

### [M5 — Skill, plugin, packaging and docs](M5.md)
Entries: 2026-10-25T15:27-0700 through 2026-10-25T15:44-0700
Outcome: complete; SKILL.md + vendor docs, `--skill`/`skill`, plugin and marketplace manifests, `pyproject.toml`, docs rewritten
- The package holds symbolic links to the skill docs (not named SKILL.md); the wheel stores files.
- The repo is its own one-plugin marketplace so the plugin can be installed; validated, never loaded.
- `pyproject.toml` retargeted pyink (parenthesized `with` in two untouched files).
- Review: 4 findings, all fixed (skill --json, exit-4 note, NOTES.md, a lost `\u003c`).

### [M6 — Migration, final verification and first release](M6.md)
Entries: 2026-10-25T15:49-0700 through 2026-10-25T16:21-0700
Outcome: complete; data migrated with matching counts, `v0.1.0` released (shell byte-identical to a local build), checkout cleaned
- SKILL.md's migration order would have overwritten the counts in NOTES.md; reordered, with a counting command for the old build's data.json.
- Cold start found five skill gaps (substring noise, `status` shape, undocumented fields, returns, PATH fallback); all fixed.
- Browser tool still refuses `file://`; loopback check, then the user opened it from disk.
- Review F4: a real export date slipped into the notebook; the privacy grep had no date patterns.

## Threads
- **Privacy of tracked files:** [design](design.md), [M4](M4.md) — the draft quoted account
  counts and had to be scrubbed; M4's privacy note first listed the private grep patterns.
  Keep examples generic, describe checks by category. [M6](M6.md): a real export date slipped
  past a pattern grep with no date patterns; the conventions arm caught it.
- **Python 3.10 support:** [M1](M1.md), [M2](M2.md), [M4](M4.md) — `build.py` needs 3.12; the
  new package and its lint rules keep to 3.10 syntax (f-string quote rule hit again in M2
  and M4).
- **Shell trust and release integrity:** [design](design.md), [M3](M3.md), [M4](M4.md) — the
  design relied on the tag ruleset; M3's review found assets aren't covered; resolved in M4
  by the user's choice of immutable releases.
- **Never deleting data:** [M2](M2.md) — the tool removes only its own `.staging-*`
  folders; rollback, the archive-name check and the failed-rollback note guard the rest.
- **Exit-code bands:** [M2](M2.md), [M4](M4.md), [M5](M5.md) — 20/21 mean "nothing done" /
  "partly done" for both import and update; M5's skill and the design give each command's
  meaning.
