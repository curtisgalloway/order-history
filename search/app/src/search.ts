// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import type { Data, Item, Order } from "./types";

/** One row in the Items view: an item, or an order whose export has no items. */
export interface ItemRow {
  key: string;
  order: Order;
  item?: Item;
  hay: string;
}

/** One card in the Orders view. */
export interface OrderRow {
  key: string;
  order: Order;
  hay: string;
  itemHays: string[];
}

export type Kind = "" | "physical" | "digital";

export interface Filters {
  terms: string[];
  store: string;
  kind: Kind;
}

export interface Index {
  items: ItemRow[];
  orders: OrderRow[];
}

export function buildIndex(data: Data): Index {
  const storeName = new Map(data.stores.map((s) => [s.id, s.name]));
  const items: ItemRow[] = [];
  const orders: OrderRow[] = [];
  for (const order of data.orders) {
    const key = order.store + ":" + order.id;
    const hay = [
      storeName.get(order.store),
      order.id,
      order.date,
      order.status,
      order.site,
      order.shipMethod,
      order.digital ? "digital kindle" : "physical",
    ]
      .join(" ")
      .toLowerCase();
    const itemHays = order.items.map((it) =>
      [it.name, it.asin, it.pid, it.department].join(" ").toLowerCase(),
    );
    orders.push({ key, order, hay, itemHays });
    if (order.items.length === 0) {
      items.push({ key, order, hay: hay + " items not in export" });
    }
    order.items.forEach((item, i) => {
      items.push({ key: key + ":" + i, order, item, hay: hay + " " + itemHays[i] });
    });
  }
  return { items, orders };
}

export function parseTerms(q: string): string[] {
  return q.toLowerCase().split(/\s+/).filter(Boolean);
}

function passes(order: Order, f: Filters): boolean {
  if (f.store && order.store !== f.store) return false;
  if (f.kind === "digital") return !!order.digital;
  if (f.kind === "physical") return !order.digital;
  return true;
}

export function filterItems(rows: ItemRow[], f: Filters): ItemRow[] {
  return rows.filter((r) => passes(r.order, f) && f.terms.every((t) => r.hay.includes(t)));
}

/** An order matches when every term is in the order fields or in any of its items. */
export function filterOrders(rows: OrderRow[], f: Filters): OrderRow[] {
  return rows.filter(
    (r) =>
      passes(r.order, f) &&
      f.terms.every((t) => r.hay.includes(t) || r.itemHays.some((h) => h.includes(t))),
  );
}

/** Whether an item inside a matching order card is one the query is about. */
export function itemHit(row: OrderRow, i: number, terms: string[]): boolean {
  const h = row.itemHays[i];
  return (
    terms.length > 0 &&
    terms.some((t) => h.includes(t)) &&
    terms.every((t) => h.includes(t) || row.hay.includes(t))
  );
}
