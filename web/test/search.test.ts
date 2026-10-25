// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

// search.ts against tests/search_cases.json, the case file search.py is also
// tested with, over the fixture orders as page.py builds them. Keeps the two
// search implementations from drifting. Run: npm test (node --test).

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { buildIndex, filterItems, parseTerms, type Kind } from "../src/search.ts";
import type { Data } from "../src/types.ts";

const repo = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const python = process.env.PYTHON ?? "python3";
const data = JSON.parse(
  execFileSync(python, [join(repo, "tests", "fixture_page_data.py")], { encoding: "utf8" }),
) as Data;
const cases = JSON.parse(readFileSync(join(repo, "tests", "search_cases.json"), "utf8"))
  .cases as { query: string; store?: string; kind?: Kind; expect: string[] }[];

test("the fixture data loaded", () => {
  assert.ok(data.orders.length > 0);
});

for (const c of cases) {
  test(`search ${JSON.stringify(c.query)} store=${c.store ?? ""} kind=${c.kind ?? ""}`, () => {
    const index = buildIndex(data);
    const rows = filterItems(index.items, {
      terms: parseTerms(c.query),
      store: c.store ?? "",
      kind: c.kind ?? "",
    });
    // search.py returns matching orders in data order; the Items view lists
    // their matching rows in the same order.
    const ids = [...new Set(rows.map((r) => r.order.id))];
    assert.deepEqual(ids, c.expect);
  });
}
