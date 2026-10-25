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
