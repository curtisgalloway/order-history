// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import { money, stampClass } from "./format";
import { itemHit, type ItemRow, type OrderRow } from "./search";
import { Thumb } from "./Thumb";
import type { Order } from "./types";

function Ext({ href, children }: { href?: string; children: React.ReactNode }) {
  return href ? (
    <a href={href} target="_blank" rel="noopener">
      {children}
    </a>
  ) : (
    <>{children}</>
  );
}

function StoreBadge({ id, name }: { id: string; name: string }) {
  return <span className={"badge store-" + id}>{name}</span>;
}

function Stamp({ status }: { status?: string }) {
  return status ? <span className={"stamp " + stampClass(status)}>{status}</span> : null;
}

/** Order-level amounts for exports without item lines. */
function SummaryLine({ order }: { order: Order }) {
  const s = order.summary;
  if (!s) return null;
  const parts = [
    ["subtotal", s.subtotal],
    ["shipping", s.shipping],
    ["tax", s.tax],
    ["discount", s.discount],
  ].filter(([, v]) => v);
  return (
    <>
      {parts.map(([label, v]) => (
        <span key={label}>
          {label} {money(v, order.currency)}
        </span>
      ))}
      {order.shipMethod && <span className="ship">{order.shipMethod}</span>}
    </>
  );
}

function OrderMeta({ order, storeName }: { order: Order; storeName: string }) {
  return (
    <>
      <StoreBadge id={order.store} name={storeName} />
      <span>{order.date}</span>
      <span>
        <Ext href={order.url}>{order.id}</Ext>
      </span>
      {order.site && order.site !== "Amazon.com" && <span>{order.site}</span>}
      {order.digital && <span className="dig">digital</span>}
    </>
  );
}

export function ItemRowView({ row, storeName }: { row: ItemRow; storeName: string }) {
  const { order, item } = row;
  const total = item ? item.total : order.total;
  return (
    <div className="item">
      <div className="thumb">
        <Thumb item={item} label={storeName} />
      </div>
      <div className="body">
        <div className="name">
          {item ? (
            <Ext href={item.url}>{item.name}</Ext>
          ) : (
            <span className="noitems">{storeName} order · item list not in export</span>
          )}
        </div>
        <div className="meta">
          <OrderMeta order={order} storeName={storeName} />
          {item?.asin && <span>{item.asin}</span>}
          {item?.pid && <span>PID {item.pid}</span>}
          {item?.department && <span>{item.department}</span>}
          {!item && <SummaryLine order={order} />}
        </div>
      </div>
      <div className="right">
        {total && <div className="price">{money(total, order.currency)}</div>}
        {item && item.qty !== "1" && <div className="qty">qty {item.qty}</div>}
        <Stamp status={order.status} />
      </div>
    </div>
  );
}

export function OrderCard({
  row,
  storeName,
  terms,
}: {
  row: OrderRow;
  storeName: string;
  terms: string[];
}) {
  const { order } = row;
  return (
    <div className="order">
      <div className="order-head">
        <div className="meta">
          <OrderMeta order={order} storeName={storeName} />
          <span>
            {order.items.length || "no"} item{order.items.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="right">
          {order.total && <div className="price">{money(order.total, order.currency)}</div>}
          <Stamp status={order.status} />
        </div>
      </div>
      {order.items.length > 0 ? (
        <ul className="order-items">
          {order.items.map((item, i) => (
            <li key={i} className={itemHit(row, i, terms) ? "hit" : undefined}>
              <div className="thumb small">
                <Thumb item={item} label={storeName} />
              </div>
              <div className="name">
                <Ext href={item.url}>{item.name}</Ext>
              </div>
              <div className="line-price">
                {item.qty !== "1" && <span className="qty">{item.qty} × </span>}
                {money(item.total, order.currency)}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="order-note meta">
          <span className="noitems">item list not in export</span>
          <SummaryLine order={order} />
        </div>
      )}
    </div>
  );
}
