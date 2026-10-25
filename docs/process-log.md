<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Process log

Where the agent's process cost time on this project. Input for improving the agent's
instructions and skills; project findings go in the backlog instead.

## 2026-10-25T12:22-0700 — user correction: over-broad privacy scan
Chapter: [design](notebook/design.md)
What happened: asked to confirm the repo was scrubbed, the agent started a script that
read every export to grep git history for addresses and order IDs. The user stopped it
and said to scrub the source and start a fresh repo instead.
Cost: one rejected tool call and a redirect.
Prevention: when history will be discarded anyway, check only the tree that will ship.
Fix belongs in: user instructions (privacy section)
Status: open

## 2026-10-25T12:22-0700 — instruction gap: quiz options that can conflict
Chapter: [design](notebook/design.md)
What happened: one quiz offered "browser only" alongside fetch actions a browser can't
do. The user picked both, and a second quiz was needed.
Cost: an extra quiz round, and a clarification request.
Prevention: check that every combination of options is buildable before asking, or
note the dependency in each option's description.
Fix belongs in: user instructions (quiz rule)
Status: open

## 2026-10-25T12:22-0700 — surprise: design draft leaked account facts
Chapter: [design](notebook/design.md)
What happened: the first draft of `docs/design.md` included real order counts and a real
product name from this session's work.
Cost: a rewrite before commit; no leak.
Prevention: grep each new doc for numbers and names from the session before writing
the commit.
Fix belongs in: project instructions (AGENTS.md "Before committing")
Status: open
