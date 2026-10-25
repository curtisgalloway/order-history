// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import type { Data } from "./types";

/**
 * The data format this page understands. order-history's page.py writes the
 * same number into the data; when they differ the page shows a message
 * instead of misreading the data. Bump both together.
 */
export const DATA_FORMAT = 1;

export type Loaded = { ok: true; data: Data } | { ok: false; message: string };

/** Parse the text of the page's order-data element and check its format. */
export function loadData(text: string | null | undefined): Loaded {
  if (!text || !text.trim()) {
    return {
      ok: false,
      message:
        "This page holds no order data. It is the empty page shell: build the page with " +
        "`order-history build` (or import an export), then open the index.html it writes.",
    };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, message: "This page's order data is damaged. Rebuild it with `order-history build`." };
  }
  const format = (parsed as { format?: unknown } | null)?.format;
  if (format !== DATA_FORMAT) {
    return {
      ok: false,
      message:
        `This page understands data format ${DATA_FORMAT}, but its data is format ` +
        `${JSON.stringify(format ?? null)}. The page and the order-history tool are from ` +
        "different versions: rebuild it with `order-history build`.",
    };
  }
  return { ok: true, data: parsed as Data };
}
