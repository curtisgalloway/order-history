<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history: developer guide

This repository is `order-history`, a command-line tool and agent skill for searching
your own order history from the exports stores let you download (Amazon's "Request My
Data" zip, Adafruit's order-history CSV). This file is for working **on the code**.

**To use the tool** (import an export, answer "when did I buy…", run `update`), follow
the skill instead: [`skills/order-history/SKILL.md`](skills/order-history/SKILL.md),
and for one store's export format and quirks,
[`skills/order-history/vendors/<store>.md`](skills/order-history/vendors/). Those files
are also what `order-history --skill` and `order-history skill <store>` print.

**Terms** (full list in [GLOSSARY.md](GLOSSARY.md)):

- **Export**: the file a store lets you download with your own orders.
- **Vendor module**: one store's code (`order_history/vendors/<id>.py`) plus its
  instruction file (`skills/order-history/vendors/<id>.md`).
- **Data folder**: where exports, caches and the built page live, outside the repository
  (`~/Documents/Order History` by default).
- **Page shell**: the search page built with no data in it; releases publish it.
- **Skill / plugin**: the agent instructions (`SKILL.md`) and Claude Code's install unit
  wrapping them (`.claude-plugin/`).

The design is [docs/design.md](docs/design.md) and the milestone plan
[docs/implementation-plan.md](docs/implementation-plan.md).

## Purchase data never enters the repository

This repo is public. No export, cache, built page or fact about one account belongs in a
tracked file. Personal notes about the exports go in the data folder's `NOTES.md`; a
clone from before the data folder may still have a gitignored `LOCAL.md` (read it first
if it exists, and see SKILL.md's migration section). Tests use invented fixtures only
(`tests/fixtures/`), with made-up order IDs like `111-1234567-1234567` and addresses at
`example.com`.

**Before every commit,** check the staged diff for personal data: email addresses,
home-directory paths, real order IDs, product names from the exports, addresses, and
counts or dates that describe one account. Use made-up examples instead.

## Layout

```
./
├── AGENTS.md, README.md, GLOSSARY.md, LICENSE, pyproject.toml
├── .claude-plugin/
│   ├── plugin.json              ← the Claude Code plugin manifest (this repo is the plugin)
│   └── marketplace.json         ← lists this repo as its own plugin source
├── skills/order-history/        ← the skill folder: what a plugin or agent loads
│   ├── SKILL.md                 ← agent instructions (printed by --skill)
│   ├── vendors/amazon.md, adafruit.md   ← per-store instructions
│   └── scripts/
│       ├── order-history        ← entry script (runs the package beside it)
│       └── order_history/
│           ├── cli.py           ← subcommands, exit codes, --json, --skill
│           ├── config.py        ← data-folder resolution
│           ├── model.py         ← the normalized order and item shape
│           ├── store.py         ← import: stage, compare, archive, swap, locks
│           ├── search.py        ← matching rules shared with the page
│           ├── page.py          ← get a page shell; shell + data → index.html
│           ├── fetching.py      ← what update's lookups share (injected network)
│           ├── agent_skill.md   ← symbolic link to ../../SKILL.md
│           └── vendors/
│               ├── __init__.py  ← VENDORS, the registry
│               ├── amazon.py, adafruit.py
│               └── amazon.md, adafruit.md   ← symbolic links to ../../../vendors/
├── web/                         ← Vite + React + TypeScript source of the page shell
├── tests/                       ← unittest, invented fixtures only
├── docs/                        ← design, plan, evidence, lab notebook, process log
└── .github/workflows/           ← ci.yml (lint, test, page), release.yml
```

The package is standard library only and supports Python 3.10 and later.

## How the parts fit

- **Vendor modules.** Each store is a module with `ID`, `NAME`, `detect`, `install`,
  `as_of`, `read`, `load`, and optionally `compare`, `gaps` and `enrich`; the contract is
  the docstring of `vendors/__init__.py`. Each returns orders in one shape
  (`model.new_order()`). A store with no imported export is skipped.
- **Adding a store:** write `vendors/<id>.py` and `skills/order-history/vendors/<id>.md`,
  add the symbolic link `order_history/vendors/<id>.md -> ../../../vendors/<id>.md`, list
  the module in `vendors/__init__.py`, and give it a badge color (`--store-<id>`) in
  `web/src/styles.css`. `tests/test_skill.py` fails until the instruction file and the
  link exist.
- **The page.** `web/` builds the page shell, the page with its
  `<script id="order-data" type="application/json">` element left empty. `page.py`
  fills it (every `<` escaped as `\u003c`) and writes `<data>/index.html` atomically.
  The data carries a `format` number: `page.py`'s `FORMAT` and `web/src/load.ts`'s
  `DATA_FORMAT` change together, and a page whose numbers differ shows a message.
- **Where the shell comes from:** the cache (`~/.cache/order-history/`), else a local
  `npm run build` in `web/` (a checkout with npm), else the `page-shell.html` attached to
  the GitHub release for this version (then cached). With none, building exits 4 and the
  old page stays.
- **The skill documents inside the package.** `--skill` reads `agent_skill.md` and
  `vendors/<id>.md` through `importlib.resources`, so an installed tool prints its own
  version's text. In the source tree they are symbolic links to the skill folder, which
  a wheel stores as plain files (`[tool.setuptools.package-data]` in `pyproject.toml`).
  The link is not named `SKILL.md` so that no agent scanning for skills finds a second
  copy. Edit `skills/order-history/SKILL.md` and the vendor `.md` files, never the links.
- **update's politeness.** The Adafruit lookups read robots.txt with their own
  User-Agent, wait at least 10 s plus jitter between requests (longer for a
  `Crawl-delay`), never refetch a cached order, and stop at the first 429/5xx; Amazon
  image scraping runs only with `--amazon-images`. Keep it that way:
  `tests/test_update.py` checks each rule with the network, clock and jitter stubbed. No
  test or manual run sends a real request to either store; `support.IsolatedTestCase`
  fails any test whose network call isn't stubbed.

## Checks

These are what CI runs (`.github/workflows/ci.yml`); run them before pushing.

```bash
python3 -m unittest discover -s tests            # also on Python 3.10
uvx pylint==4.1.3 skills/order-history/scripts/order_history skills/order-history/scripts/order-history tests
uvx pyink --check skills tests skills/order-history/scripts/order-history
npm --prefix web ci && npm --prefix web run build && npm --prefix web test
ORDER_HISTORY_TEST_SHELL="$PWD/web/dist/index.html" python3 -m unittest discover -s tests -p test_page.py
```

- Pylint uses Google's pylintrc with `max-line-length=88` (CI downloads it at a fixed
  commit). Keep to Python 3.10 syntax: no reuse of an f-string's own quote character
  inside it. pyink takes its target version from `requires-python` in `pyproject.toml`.
- `npm --prefix web test` runs `tests/search_cases.json` against `web/src/search.ts`, so
  the page and `search.py` can't drift.
- The plugin manifests: `claude plugin validate .claude-plugin/plugin.json` and
  `claude plugin validate .claude-plugin/marketplace.json` (not in CI).
- npm dependencies are pinned to exact versions (each at least two weeks old when
  chosen) with a lockfile.
- Test stubs that narrow `PATH` call other tools by absolute path.

## Releases

The version is `order_history.__version__`. `pyproject.toml` reads it, and
`.claude-plugin/plugin.json`'s `version` must equal it (a test checks), so change both
together. Pushing the tag `v<version>` runs `release.yml`, which checks the tag against
the package, builds the page shell and attaches it to the release as `page-shell.html`.
Releases are immutable once published.
