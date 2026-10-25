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

## 2026-10-25T13:56-0700 — surprise: pitch gate blocked M1 in a project with an approved design
Chapter: [M1](notebook/M1.md)
What happened: the first M1 session's first write (a `date` call chained with reads) was
refused by a PreToolUse hook: "PITCH GATE: ... looks like a new project (no PITCH.md, 3
commit(s), directory under 14 days old). Nothing gets written here until PITCH.md
exists." The hook keys on the directory's age and commit count, not on whether a design
exists, and its named escape file (`.no-pitch`) can't be created under the gate either.
Cost: one milestone subagent launch, which stopped and reported back; a round trip
through the orchestrator to the user.
Prevention: have the hook treat an approved `docs/design.md` (or an existing plan) as
past the pitch stage, and let it allow creating its own escape file.
Fix belongs in: tool (the pitch-gate hook in agent-config)
Status: resolved for this repo: user-created, gitignored .no-pitch; hook gap noted: it blocks creating its own named escape file

## 2026-10-25T14:04-0700 — failed command: pylint quote rules vs Python 3.10 f-strings
Chapter: [M1](notebook/M1.md)
What happened: Google's pylintrc flagged single quotes inside f-strings
(`inconsistent-quotes`); rewriting them with `.format()` then hit
`consider-using-f-string`. Python 3.10 can't reuse an f-string's own quote.
Cost: two extra lint-and-fix rounds.
Prevention: when 3.10 is supported, pull subscripted values into locals before the
f-string from the start.
Fix belongs in: user instructions (Python conventions)
Status: open

## 2026-10-25T14:22-0700 — instruction not followed: notebook timestamps guessed
Chapter: [M2](notebook/M2.md)
What happened: five M2 entries were written with a guessed time (14:40) in the same
command that read the clock (14:22), instead of reading the clock first.
Cost: one fix-up edit before anything read the entries.
Prevention: read `date` in its own call before composing timestamped entries.
Fix belongs in: skill (lab-notebook, "Timestamps")
Status: open

## 2026-10-25T14:28-0700 — failed command: zsh does not word-split a command in a variable
Chapter: [M2](notebook/M2.md)
What happened: `G="git -C <path>"; $G diff --cached ...` failed with "no such file or
directory: git -C <path>", leaving an empty diff; the review planner then chose the light
tier for "0 changed lines".
Cost: one rerun; a wrong plan would have run one reviewer instead of seven had it not been
noticed.
Prevention: spell commands out (the Bash tool runs zsh); and check the diff is non-empty
before planning a review.
Fix belongs in: skill (review-swarm, step 1: refuse to plan on an empty diff)
Status: open

## 2026-10-25T14:46-0700 — surprise: Claude in Chrome refuses file:// pages
Chapter: [M3](notebook/M3.md)
What happened: the M3 acceptance check opens `<data>/index.html` from disk, but the
browser tool answered "Can't interact with browser-internal or unparseable URLs" for every
`file://` URL. The pages were served on 127.0.0.1 with `python3 -m http.server` instead.
Cost: two failed navigations; the `file://` case itself stays unchecked by the agent.
Prevention: say in the plan's manual checks that a page meant for `file://` is checked
over a loopback server when the browser tool can't open files (or turn on the extension's
"Allow access to file URLs").
Fix belongs in: tool (Claude in Chrome file URL access) / skill (project-plan manual checks)
Status: open

## 2026-10-25T14:46-0700 — instruction gap: required-check names in the plan
Chapter: [M3](notebook/M3.md)
What happened: the plan said to re-run `harden_repo.sh` with `lint test page`, but `test`
is a matrix job, which GitHub reports as `test (3.10)` and `test (3.x)`. A bare `test`
context never reports, so it would have blocked every merge.
Cost: none (found by reading the script's header before running it); would have cost a
blocked PR and another settings change.
Prevention: when a plan names required checks, list them as GitHub reports them
(`gh run view <id> --json jobs --jq '.jobs[].name'`).
Fix belongs in: skill (project-plan, or github-repo-hardening's usage note)
Status: open

## 2026-10-25T14:46-0700 — failed command: a stub executable with PATH narrowed to itself
Chapter: [M3](notebook/M3.md)
What happened: a test's fake `npm` script ran with PATH set to its own folder, so its
`mkdir` and `cp` failed with exit 127.
Cost: one test-fix round.
Prevention: stub scripts call tools by absolute path when the test narrows PATH.
Fix belongs in: project instructions (testing notes)
Status: open

## 2026-10-25T14:53-0700 — surprise: review tier chosen by words in deleted files
Chapter: [M3](notebook/M3.md)
What happened: the review planner chose the full tier because its concurrency and
secrets/auth triggers matched `ThreadPoolExecutor` and `Authorized` in `search/` files the
change only deletes. The full tier still found the two medium findings, so no harm here,
but deleted lines are not risky code.
Cost: about five extra cheap arms.
Prevention: have the planner ignore removed lines (or files listed with `D`) when matching
risk triggers.
Fix belongs in: skill (review-swarm, `swarm.py plan`)
Status: open

## 2026-10-25T15:11-0700 — failed command: zsh does not word-split a command in a variable (again)
Chapter: [M4](notebook/M4.md)
What happened: a manual-run loop over `"update --dry-run"`-style strings ran
`order-history $args`; zsh passed each whole string as one argument and argparse
refused it (exit 2), three runs wasted. The M2 entry of the same shape is still open.
Cost: one rerun.
Prevention: write each command out, or use an array (`args=(update --dry-run)`;
`"${args[@]}"`); in zsh `${=args}` splits explicitly.
Fix belongs in: user instructions (shell command style: "the Bash tool runs zsh")
Status: open

## 2026-10-25T15:21-0700 — surprise: a privacy note that quoted its own grep patterns
Chapter: [M4](notebook/M4.md)
What happened: the M4 evidence file's "Privacy check" listed the patterns grepped for,
and those patterns were the private domain, a LAN prefix and the local username, in a file
bound for a public repo. The staged-diff grep itself caught it before the commit.
Cost: one rewrite; no leak.
Prevention: describe a privacy check by category ("private host names, LAN addresses"),
never by the literal patterns; the pattern list belongs in the user's instructions only.
Fix belongs in: user instructions (privacy section: "Grep the body for these patterns")
Status: open
