<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Order history search

Search everything you have ever bought online, across stores, in one place. You
download your own order history from each store; you (or your coding agent) import it
with one command. The tool keeps every store's orders in a **data folder** on your
machine, answers questions about them from the command line, and writes a single
`index.html` that opens straight from disk: live search, product thumbnails, a per-store
filter, and an items or one-card-per-order view.

**Terms** (more in [GLOSSARY.md](GLOSSARY.md)):

- **Export**: the file or files a store lets you download with your own order history.
- **DSAR**: "data subject access request", Amazon's *Request My Data* export, a zip of
  CSV files.
- **ASIN**: Amazon's product ID, used to link to and show product images.
- **Data folder**: where your exports, caches and the built page live, outside this
  repository (`~/Documents/Order History` unless you choose another).
- **Page shell**: the search page with no data in it, published with each release; the
  tool fills in your orders.
- **Skill**: a Markdown file of instructions (`SKILL.md`) a coding agent loads to learn
  a task. Claude Code, Codex and Antigravity read the same format.
- **Plugin**: Claude Code's install unit, a folder of skills plus a manifest.

## Privacy

The page and the tool make no data requests: your orders stay in the data folder. The
only network traffic is product thumbnails on the page, the one-time download of the
page shell, and `update`'s lookups (below).

**When you use it through a coding agent, the results it reads are sent to the model
provider** like the rest of the conversation: search results, the orders it looks up,
import reports. The skill tells the agent to fetch only what a question needs, but
anything it reads leaves your machine.

## Supported stores

| Store | What to download | What you get |
| --- | --- | --- |
| Amazon | *Request My Data* → "Your Orders" (arrives as a zip, by email, after a few days) | Every item, physical and digital |
| Adafruit | Account → Order History → download CSV | One entry per order (item lists come with `update`, below) |

A store you haven't imported is skipped, so you can use either one alone. Each store's
details are in [`skills/order-history/vendors/`](skills/order-history/vendors/).

## Install

Needs Python 3.10 or later, and nothing else. Pick one:

- **As a Claude Code plugin.** In Claude Code:

  ```
  /plugin install order-history --marketplace curtisgalloway/order-history
  ```

  Or from your shell:
  `claude plugin marketplace add curtisgalloway/order-history`, then
  `claude plugin install order-history@order-history`. The plugin adds the skill; the
  agent runs the tool from the plugin's own copy.
- **As a command, with [uv](https://docs.astral.sh/uv/):**

  ```bash
  uv tool install git+https://github.com/curtisgalloway/order-history
  ```

  (or `uv tool install .` in a clone). This puts `order-history` on your `PATH`.
- **From a clone**, with no install: run `skills/order-history/scripts/order-history`.

For another agent (Codex, Antigravity, …), put the skill folder where that agent looks
for skills: copy or link `skills/order-history/` into its skills folder. With the
command installed, `order-history --skill` prints the skill document, so
`order-history --skill > <skills folder>/order-history/SKILL.md` also works; the agent
then gets each store's notes from `order-history skill <store>`.

Node is not needed: the tool downloads the page shell for its version once from this
project's GitHub release and caches it. (Until the first release is published that
download fails, so building the page needs Node and npm, from a clone.)

## Use

With an agent, say what you want: "import ~/Downloads/<the export>", "when did I buy
that soldering iron?", "fill in the Adafruit item lists". By hand:

```bash
order-history init
order-history import ~/Downloads/<the export zip or CSV>
open ~/Documents/"Order History"/index.html
```

| Command | What it does |
| --- | --- |
| `init [--data-dir PATH]` | Create the data folder and remember it |
| `import PATH [--dry-run] [--force]` | Recognize the store, archive the previous export, install the new one, report what changed, rebuild the page |
| `search TERMS… [--store ID] [--kind physical\|digital]` | Items matching every term, grouped by order |
| `order ID [--store ID]` | One order |
| `status` | What is imported, what is missing, when the page was built |
| `update [--email E] [--amazon-images] [--dry-run]` | Fill in what the exports leave out (below), then rebuild |
| `build` | Rebuild the page by hand |
| `skill [STORE]`, `--skill` | Print the agent instructions |

Every command takes `--json` (one JSON document on stdout) and `--data-dir`. The exit
codes, per command, are in [SKILL.md](skills/order-history/SKILL.md#exit-codes).

### update

```bash
echo you@example.com > ~/Documents/"Order History"/adafruit/lookup_email.txt
order-history update
```

- **Adafruit item lists** (on by default). Adafruit's guest order-status page shows an
  order's items given the account email and order number. `update` reads robots.txt
  first, sends one request at a time at least 10 seconds apart, looks up only orders it
  hasn't already, and stops at the first sign of throttling. The email comes from
  `--email`, `$ADAFRUIT_EMAIL` or `adafruit/lookup_email.txt` in the data folder.
- **Amazon product images** (only with `--amazon-images`). This scrapes amazon.com
  product pages, which may be against Amazon's conditions of use, so it is off unless
  you ask for it. Without the flag no request goes to Amazon.

`--dry-run` says how many lookups are missing without sending anything. With nothing
missing, `update` sends no request and exits 0. It exits 20 when nothing was saved (a
site throttled, robots.txt said no, or every lookup failed), 21 when it saved some
lookups and then stopped (run it again later), and 3 when Adafruit orders need items and
there is no lookup email.

## Your data stays out of git

Your exports, caches and the built page live in the data folder, outside any checkout.
`.gitignore` still covers the old in-checkout locations (`Your Amazon Orders/`,
`Adafruit/`, `search/`, `archive/`, `LOCAL.md`), so a clone that still holds data from
before doesn't leak it.
[SKILL.md](skills/order-history/SKILL.md#migrating-from-an-in-checkout-layout) describes
moving that data into a data folder. Check `git status` before committing anyway.

## Development

[AGENTS.md](AGENTS.md) is the developer guide: the layout, the checks CI runs, how to add
a store, and the privacy rules for commits.

## License

Apache 2.0 — see [LICENSE](LICENSE).
