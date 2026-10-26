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

## 2026-10-25T15:37-0700 — failed command: zsh does not word-split a command in a variable (third time)
Chapter: [M5](notebook/M5.md)
What happened: an install check put `env -i PATH=... HOME=...` in `E` and ran `$E
order-history status`; zsh ran the whole string as one command name ("no such file or
directory: env -i PATH=..."), so every check in the batch failed with exit 127. The two
earlier entries of this shape are still open.
Cost: one rerun, through a small wrapper script.
Prevention: the same as before (arrays, or a wrapper script); the instruction should say it
in the shell-command rules, since reading the open entries didn't stop the third repeat.
Fix belongs in: user instructions (shell command style: "the Bash tool runs zsh")
Status: open

## 2026-10-25T15:37-0700 — surprise: adding pyproject.toml retargeted the formatter
Chapter: [M5](notebook/M5.md)
What happened: `pyink --check` failed on two untouched files once `pyproject.toml` existed,
because pyink takes its target version from `requires-python`.
Cost: one format run and a note; two unrelated files in the diff.
Prevention: when adding a `pyproject.toml` to a repo that already runs a formatter, rerun
the formatter over the whole tree in the same step and expect changes.
Fix belongs in: project instructions (AGENTS.md "Checks")
Status: open

## 2026-10-25T15:44-0700 — surprise: a written file lost a `\u` escape
Chapter: [M5](notebook/M5.md)
What happened: AGENTS.md was written with the text `` `\u003c` `` and the file held a bare
`` `<` ``: the six-character escape was decoded on the way to disk. Nothing checked it; the
review's docs arm found the sentence had become a no-op ("`<` escaped as `<`").
It happens before any tool runs: the notebook entries describing it, written through a shell
heredoc, lost the escape the same way; only text built in Python with `chr(92)` kept it.
Cost: one review finding and two fix rounds.
Prevention: after writing a file whose text must hold a literal `\uXXXX` (or other escape),
grep the file for it; or write such lines with a script that spells the backslash out.
Fix belongs in: tool (the harness's handling of `\u` sequences in tool input) / user instructions (the "non-printing characters" rule could mention it)
Status: open

## 2026-10-25T15:59-0700 — surprise: Claude in Chrome refuses file:// pages (again)
Chapter: [M6](notebook/M6.md)
What happened: M6's criterion "the page opens from `<data>/index.html`" met the same
refusal as M3; the M3 entry is still open. Checked over a loopback server again, and the
`file://` open went to the user as a manual check.
Cost: one failed navigation; the criterion needs a human step.
Prevention: the same as the M3 entry. The plan should have written the criterion as
"over loopback, plus one manual `file://` open" from the start, since M3 already knew.
Fix belongs in: tool (Claude in Chrome file URL access) / skill (project-plan: carry known
tool limits from earlier milestones into later criteria)
Status: open

## 2026-10-25T15:59-0700 — failed command: BSD `head -c 0`
Chapter: [M6](notebook/M6.md)
What happened: a no-op `head -c 0 /dev/null` at the end of a privacy breakdown failed
("illegal byte count -- 0") and turned the whole call's exit status to 1. The useful output
had printed, so nothing was lost.
Cost: a confusing error on a command that had worked.
Prevention: don't append filler commands; on macOS, `head -c` needs a positive count.
Fix belongs in: user instructions ("On macOS: BSD userland flags")
Status: open

## 2026-10-25T15:59-0700 — instruction gap: the migration steps' order clobbered the notes
Chapter: [M6](notebook/M6.md)
What happened: SKILL.md said to "note" the counts in step 1 and `cp LOCAL.md NOTES.md` in
step 5. The plan said to record the counts in `NOTES.md` before migrating. Followed
literally, step 5 overwrites the counts. Caught before running step 5, by reading ahead.
Cost: none in data; the skill needed a rewrite of four steps.
Prevention: when a skill step writes a file, check what earlier steps put there. The skill
itself is now fixed (project change, recorded in the M6 evidence).
Fix belongs in: skill (order-history SKILL.md, fixed in M6)
Status: fixed in skills/order-history/SKILL.md (M6)

## 2026-10-25T16:05-0700 — instruction not followed: a real export date in the notebook
Chapter: [M6](notebook/M6.md)
What happened: a notebook entry named the real archived export's folder, date included.
The privacy grep built patterns for order IDs, product names, addresses, emails, paths and
counts, but none for dates, though AGENTS.md lists "counts or dates that describe one
account". The review's conventions arm caught it before the commit.
Cost: one review finding and an in-place fix to an append-only chapter.
Prevention: build the privacy patterns from AGENTS.md's list item by item, dates included
(the export's `as_of` dates, retrieval dates, archive folder names); and write
placeholders (`<date>`) while drafting rather than scrubbing later.
Fix belongs in: project instructions (AGENTS.md "Before committing": name the date sources)
Status: open

## 2026-10-25T16:21-0700 — failed command: editing a file written through the shell
Chapter: [M6](notebook/M6.md)
What happened: `docs/evidence/M6.md` was created with the file-writing tool, then changed
by shell commands and edited again. The edit tool refused twice ("File has not been read
yet") until the file was read again; the first refusal was a recheck note that had to be
rewritten.
Cost: two failed edits and two extra reads.
Prevention: after changing a file with a shell command, read the region again before using
the edit tool on it; or make all changes to that file through one mechanism.
Fix belongs in: user instructions (the "On Claude Code" tool notes)
Status: open

## 2026-10-25T22:10-0700 — instruction not followed: a notebook timestamp typed, not read
Chapter: [M7](notebook/M7.md)
What happened: three decision entries were stamped 22:20 in the same command that first
read the clock, which then said 22:10. The lab-notebook skill says to take every
timestamp from the system clock at the moment of writing.
Cost: a correction entry in an append-only chapter.
Prevention: read the clock in a separate step before writing the heading, or write the
entry with the shell substituting the time, as the correction did.
Fix belongs in: skill (lab-notebook: suggest generating the heading from `date`)
Status: open

## 2026-10-25T22:20-0700 — failed command: a scripted edit after the formatter rewrapped its target
Chapter: [M7](notebook/M7.md)
What happened: a Python find-and-replace over a test file asserted on a line pyink had
rewrapped since it was written; the first of its two edits had already been saved, so the
file was half-edited until a second script fixed the rest.
Cost: one failed command and a re-check of which edit applied.
Prevention: run the formatter before scripting edits, and match on text read after it; or
check every pattern before writing any.
Fix belongs in: user instructions (notes on scripted edits)
Status: open

## 2026-10-25T23:15-0700 — privacy slip: observed page values copied into examples
Chapter: [M8](notebook/M8.md)
What happened: the first draft of the catch-up steps used the observed real order's page
text (its order date, delivery date and a price) and the existing `add` example's amounts
as examples. A staged-diff date grep caught the dates before the first
commit. The orchestrator later found that the existing example amounts and fixtures (from
the M7 design and M7) also came from that order; replaced in M8. Then the first rewording
of the run in the evidence still stated a count, caught by two review arms, and the fix for
that still used a number word, caught by the recheck.
Cost: rewrites in three passes, a review finding and a recheck finding.
Prevention: when the brief or a design quotes values observed on a real page, use them as
facts about the page's shape only, and write every example with invented values from the
start. Describe a real run without numbers or number words.
Fix belongs in: skill (project-plan: the privacy step should name observed values and
number words, not only IDs, names and dates)
Status: open
