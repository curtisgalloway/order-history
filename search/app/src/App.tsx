// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { useDeferredValue, useLayoutEffect, useMemo, useRef, useState } from "react";
import data from "./generated/data.json";
import { ItemRowView, OrderCard } from "./Rows";
import {
  buildIndex,
  filterItems,
  filterOrders,
  parseTerms,
  type Filters,
  type Kind,
} from "./search";

type View = "items" | "orders";

const index = buildIndex(data);
const storeName = Object.fromEntries(data.stores.map((s) => [s.id, s.name]));

function Seg<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} className={v === value ? "on" : ""} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

function Stats() {
  const dates = data.orders.map((o) => o.date).filter(Boolean).sort();
  return (
    <div className="stats">
      {data.stores.map((s) => (
        <span key={s.id}>
          <b>{data.orders.filter((o) => o.store === s.id).length.toLocaleString()}</b> {s.name}{" "}
          orders
        </span>
      ))}
      <span>
        <b>{index.items.length.toLocaleString()}</b> entries
      </span>
      <span>
        <b>
          {dates[0]} – {dates[dates.length - 1]}
        </b>
      </span>
    </div>
  );
}

export function App() {
  const [query, setQuery] = useState("");
  const [store, setStore] = useState("");
  const [kind, setKind] = useState<Kind>("");
  const [view, setView] = useState<View>("items");
  const deferredQuery = useDeferredValue(query);

  const filters: Filters = useMemo(
    () => ({ terms: parseTerms(deferredQuery), store, kind }),
    [deferredQuery, store, kind],
  );
  const itemRows = useMemo(
    () => (view === "items" ? filterItems(index.items, filters) : []),
    [view, filters],
  );
  const orderRows = useMemo(
    () => (view === "orders" ? filterOrders(index.orders, filters) : []),
    [view, filters],
  );
  const count = view === "items" ? itemRows.length : orderRows.length;
  const total = view === "items" ? index.items.length : index.orders.length;

  // The list's distance from the top of the page, for the window virtualizer.
  // Re-measured when the header or controls change height (web fonts
  // arriving, the controls wrapping on a narrow window).
  const listRef = useRef<HTMLUListElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const controlsRef = useRef<HTMLDivElement>(null);
  const [listTop, setListTop] = useState(0);
  useLayoutEffect(() => {
    const measure = () =>
      setListTop((listRef.current?.getBoundingClientRect().top ?? 0) + window.scrollY);
    measure();
    const ro = new ResizeObserver(measure);
    for (const el of [headerRef.current, controlsRef.current]) if (el) ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const virtualizer = useWindowVirtualizer({
    count,
    estimateSize: () => (view === "items" ? 121 : 160),
    overscan: 6,
    scrollMargin: listTop,
    getItemKey: (i) => (view === "items" ? itemRows[i].key : orderRows[i].key),
  });

  // A new result set starts at its top, not wherever the old one was scrolled.
  useLayoutEffect(() => {
    const controlsHeight = controlsRef.current?.offsetHeight ?? 0;
    const top = listTop - controlsHeight;
    if (window.scrollY > top) window.scrollTo({ top });
  }, [filters, view, listTop]);

  const stores: [string, string][] = [["", "All"], ...data.stores.map((s): [string, string] => [s.id, s.name])];

  return (
    <div className="slip">
      <header ref={headerRef}>
        <div>
          <div className="eyebrow">personal data exports</div>
          <h1>
            Order <span className="hollow">Manifest</span>
          </h1>
        </div>
        <div className="barcode">
          <small>ORDER·ARCHIVE</small>
        </div>
        <Stats />
      </header>

      <div className="controls" ref={controlsRef}>
        <div className="searchwrap">
          <input
            id="q"
            type="search"
            placeholder="search products, order IDs, ASINs, stores, years…"
            autoFocus
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="segs">
          <Seg label="Store" value={store} options={stores} onChange={setStore} />
          <Seg<Kind>
            label="Type"
            value={kind}
            options={[
              ["", "All"],
              ["physical", "Physical"],
              ["digital", "Digital"],
            ]}
            onChange={setKind}
          />
          <Seg<View>
            label="View"
            value={view}
            options={[
              ["items", "Items"],
              ["orders", "Orders"],
            ]}
            onChange={setView}
          />
        </div>
        <div className="countline">
          {count === total ? (
            <>
              {total.toLocaleString()} {view}
            </>
          ) : (
            <>
              <b>{count.toLocaleString()}</b> {count === 1 ? view.slice(0, -1) : view} match
            </>
          )}
        </div>
      </div>

      <ul id="results" ref={listRef} style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((vi) => (
          <li
            key={vi.key}
            data-index={vi.index}
            ref={virtualizer.measureElement}
            style={{ transform: `translateY(${vi.start - virtualizer.options.scrollMargin}px)` }}
          >
            {view === "items" ? (
              <ItemRowView
                row={itemRows[vi.index]}
                storeName={storeName[itemRows[vi.index].order.store]}
              />
            ) : (
              <OrderCard
                row={orderRows[vi.index]}
                storeName={storeName[orderRows[vi.index].order.store]}
                terms={filters.terms}
              />
            )}
          </li>
        ))}
      </ul>

      {count === 0 && (
        <div className="empty">
          <div className="big">Empty box</div>
          <div>nothing matches — try fewer or shorter terms</div>
        </div>
      )}

      <footer>
        <span>Sources: {data.stores.map((s) => s.source).join(" · ")}</span>
        <span>
          built {data.generated} · regenerate: python3 search/build.py
        </span>
      </footer>
    </div>
  );
}
