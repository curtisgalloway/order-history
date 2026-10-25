<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# design — Agent-first restructure

Goal: design phase 1 (import downloaded exports) of the agent-first order history.
Verdict record: [design](../design.md), then the implementation plan.

## 2026-10-25T12:21-0700 — opening
Starting revision: `a329f8b` on `main`. Pre-existing changes: none.
Approach: record the decisions reached in conversation as `docs/design.md`, stop for the
user's approval, then derive the implementation plan.

## 2026-10-25T12:21-0700 — direction: update from inside the app
The user asked to update everything from the app itself. A quiz answer chose
"browser only" and also ticked fetching Adafruit items and Amazon images; the two
conflict.

## 2026-10-25T12:21-0700 — surprise: no CORS on either store
Probed adafruit.com (POST to the order-status form and a preflight request) and
amazon.com: neither sends `Access-Control-Allow-*` headers. A page can't read either
store's responses, so in-page fetching needs a server or an extension.

## 2026-10-25T12:21-0700 — dead end: server, extension, hosted helper, email
Brainstormed a localhost server (manual or launchd), a browser extension, a browser-only
page, and a hosted page with a local helper. Then the user reframed it as agent-first.
Scheduled updates were dropped: getting an export needs a login and clicks. Email was
dropped: Amazon's confirmation emails no longer carry full details.

## 2026-10-25T12:21-0700 — decision: agent + CLI + static page; per-vendor modules
User direction: a module per vendor; import downloaded files first, automate downloads
later (phase 2). The data folder is a setting, defaulting to `~/Documents/Order History`.
The Node-free page shell is in phase 1.

## 2026-10-25T12:22-0700 — correction of the design draft
The first draft quoted this account's order counts and a product name. Both were replaced
with generic wording, per the AGENTS.md privacy rule.

## 2026-10-25T12:22-0700 — checkpoint
State: design drafted, waiting for the user's approval. Next: derive the implementation
plan once approved.

## 2026-10-25T13:27-0700 — direction: don't commit the page shell
The user rejected committing the built shell. R7 now gets it from a version-keyed cache,
a local build when Node is available, or the release asset `page-shell.html`. The data
gains a `format` number so a mismatched shell fails clearly.

## 2026-10-25T13:27-0700 — decision: design approved
The user approved the rest of the design ("otherwise approved"). Design gate satisfied
at this revision; next is deriving the implementation plan.

## 2026-10-25T13:29-0700 — checkpoint (closing)
State: complete. The design is approved and `docs/implementation-plan.md` defines M1–M6
(package and read-only commands → import → Node-free page → update → skill and plugin →
migration and release). Next: with the user's go-ahead, push `design` and merge it, then
start M1 on `m1-package`.
