// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

// The page's data check: an empty element, damaged JSON and a format
// mismatch each give a message instead of a broken page.

import assert from "node:assert/strict";
import { test } from "node:test";
import { DATA_FORMAT, loadData } from "../src/load.ts";

const good = { format: DATA_FORMAT, generated: "2025-01-01", stores: [], orders: [] };

test("matching format loads", () => {
  assert.deepEqual(loadData(JSON.stringify(good)), { ok: true, data: good });
});

test("mismatched format gives the mismatch message", () => {
  const got = loadData(JSON.stringify({ ...good, format: DATA_FORMAT + 1 }));
  assert.equal(got.ok, false);
  assert.match(!got.ok ? got.message : "", /understands data format 1, but its data is format 2/);
});

test("missing format is a mismatch", () => {
  const got = loadData(JSON.stringify({ stores: [], orders: [] }));
  assert.match(!got.ok ? got.message : "", /its data is format null/);
});

test("empty element: the shell itself", () => {
  for (const text of [null, undefined, "", "  \n"]) {
    const got = loadData(text);
    assert.match(!got.ok ? got.message : "", /holds no order data/);
  }
});

test("damaged JSON", () => {
  const got = loadData("{not json");
  assert.match(!got.ok ? got.message : "", /damaged/);
});

test("non-object JSON", () => {
  for (const text of ["null", "42", '"x"', "[]"]) {
    assert.equal(loadData(text).ok, false, text);
  }
});
