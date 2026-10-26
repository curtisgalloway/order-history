<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# design-order-pages — Catching up from order pages

## 2026-10-25T21:40-0700 — observation: order pages need no new sign-in
Driven from the agent's browser tab, the order list and an order's details page both
opened without a sign-in prompt, unlike the links in Amazon's emails. The details page
marks its parts with `data-component` attributes. The `quantity` component was empty;
the quantity is a badge on the item image. Item prices appear twice in the page text.

## 2026-10-25T21:45-0700 — decision: saved orders look the same; run only when asked
User decisions: a saved order is not marked on the page or in results. Catch-up runs
only when asked; with data over a month old, the agent may suggest a refresh once per
conversation. Order confirmation emails are a signal only (no item details).

## 2026-10-25T21:52-0700 — builder check
A fresh reviewer asked three questions, all settled without the user: no `summary` on
saved orders (the page draws one whenever present, and exported Amazon orders have
none); images merged inside the Amazon module so saved items get thumbnails; known IDs
checked with `order-history order <id>` rather than a new command.

## 2026-10-25T21:56-0700 — checkpoint (closing)
State: design approved by the user ("approved"); M7 (`add`, merging, pruning) and M8
(skill flow, one real run) added to the plan. Next: M7 on `m7-saved-orders`.
