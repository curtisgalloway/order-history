# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Build search/index.html from the order-history exports.

Each store has a loader that turns its export into the same shape: a list of
orders, each with zero or more items. The loaders' output is written to
app/src/generated/data.json, and the React app in app/ is then built by Vite
into one self-contained search/index.html (data embedded, no server needed).

  python3 search/build.py              # data + page
  python3 search/build.py --data-only  # data.json only (for `npm run dev`)

Adding a store: write a load_<store>() returning orders in the shape
documented on new_order(), and add it to STORES.
"""

import argparse
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
APP = os.path.join(HERE, "app")
DATA_JSON = os.path.join(APP, "src", "generated", "data.json")
IMAGES_JSON = os.path.join(HERE, "images.json")
OUT_HTML = os.path.join(HERE, "index.html")

AMAZON_ORDERS_CSV = os.path.join(BASE, "Your Amazon Orders", "Order History.csv")
AMAZON_DIGITAL_CSV = os.path.join(
    BASE, "Your Amazon Orders", "Digital Content Orders.csv"
)
ADAFRUIT_CSV = os.path.join(BASE, "Adafruit", "order_history.csv")
ADAFRUIT_ITEMS_JSON = os.path.join(BASE, "Adafruit", "items.json")

SENTINELS = {"", "Not Available", "Not Applicable"}

# Terminal "everything went fine" states get no stamp. Amazon's Authorized is
# its payment term for an order still in flight.
STATUS_DISPLAY = {
    "Closed": "",
    "SUCCESS": "",
    "Shipped": "",
    "Authorized": "In progress",
}


def clean(v):
    v = (v or "").strip()
    return "" if v in SENTINELS else v


def money(v):
    """Normalize a money field to "12.34", or "" when absent.

    Strips Excel armoring ("'-2.2'" -> "-2.20"), thousands separators
    ("1,234.56" -> "1234.56") and trailing precision ("42.0000" -> "42.00").
    """
    v = clean(v).strip("'").strip()
    if not v:
        return ""
    try:
        return f"{float(v.replace(",", "")):.2f}"
    except ValueError:
        return v


def status(v):
    v = clean(v)
    return STATUS_DISPLAY.get(v, v)


def new_order(store, order_id, date, **kw):
    """One order. Items are appended to order["items"] by the loader.

    Fields: store, id, date (YYYY-MM-DD), status ("" = normal), currency,
    total ("" = sum of item totals), digital, site, url, shipMethod,
    summary ({subtotal, shipping, tax, discount}, only when the export has
    order-level amounts), items.
    """
    order = {
        "store": store,
        "id": order_id,
        "date": date,
        "status": "",
        "currency": "USD",
        "total": "",
        "digital": False,
        "site": "",
        "url": "",
        "shipMethod": "",
        "summary": None,
        "items": [],
    }
    order.update(kw)
    return order


def new_item(name, **kw):
    item = {
        "name": name or "(no product name)",
        "asin": "",
        "qty": "1",
        "unit": "",
        "total": "",
        "url": "",
    }
    item.update(kw)
    return item


def _amazon_rows(path, digital):
    """Group one Amazon CSV's item rows into orders."""
    orders = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            oid = clean(r["Order ID"])
            if digital:
                cur = clean(r["Price Currency Code"]) or "USD"
                qty, total, unit = clean(r["Quantity Ordered"]), money(r["Price"]), ""
                site = clean(r["Marketplace"])
            else:
                cur = clean(r["Currency"]) or "USD"
                qty = clean(r["Original Quantity"])
                total, unit = money(r["Total Amount"]), money(r["Unit Price"])
                site = clean(r["Website"])
            order = orders.get(oid)
            if order is None:
                order = orders[oid] = new_order(
                    "amazon",
                    oid,
                    clean(r["Order Date"])[:10],
                    status=status(r["Order Status"]),
                    currency=cur,
                    digital=digital,
                    site=site,
                    url=""
                    if digital or not oid
                    else "https://www.amazon.com/gp/your-account/order-details"
                    f"?orderID={oid}",
                )
            asin = clean(r["ASIN"])
            order["items"].append(
                new_item(
                    clean(r["Product Name"]),
                    asin=asin,
                    qty=qty or "1",
                    unit=unit,
                    total=total,
                    url=f"https://www.amazon.com/dp/{asin}" if asin else "",
                    # Exports from late 2026 on; absent in older ones.
                    department=clean(r.get("Department")),
                )
            )
    return list(orders.values())


def load_amazon():
    orders = []
    for path, digital in ((AMAZON_ORDERS_CSV, False), (AMAZON_DIGITAL_CSV, True)):
        if os.path.exists(path):
            orders += _amazon_rows(path, digital)

    images = {}
    if os.path.exists(IMAGES_JSON):
        with open(IMAGES_JSON, encoding="utf-8") as f:
            images = json.load(f)
    for order in orders:
        for item in order["items"]:
            info = images.get(item["asin"])
            if info and info["src"] == "i":
                item["image"] = info["id"]
            elif info and info["src"] in (None, "tbd"):
                # Known miss on the P/ endpoint: show the placeholder directly.
                item["noImage"] = True
    return orders


def _adafruit_text(v):
    """Undo the Adafruit export's mangling of shipping-method text.

    The export replaces "-" and "=" with spaces and leaves (sometimes
    truncated) HTML in the shipping method.
    """
    v = re.sub(r"<[^>]*>?", "", clean(v))
    return re.sub(r"\s+", " ", v).strip()


def load_adafruit(with_items=True):
    """Adafruit's order-history CSV: one row per order, no item lines.

    The export writes "-" as a space: order IDs come out as
    "1234567 1234567890" and dates as "2024 01 31 12:00:00". Item lines come
    from Adafruit/items.json, written by fetch_adafruit_items.py, when present.
    """
    if not os.path.exists(ADAFRUIT_CSV):
        return []
    fetched = {}
    if with_items and os.path.exists(ADAFRUIT_ITEMS_JSON):
        with open(ADAFRUIT_ITEMS_JSON, encoding="utf-8") as f:
            fetched = json.load(f)
    orders = []
    with open(ADAFRUIT_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            oid = "-".join(clean(r["order_id"]).split())
            date = "-".join(clean(r["date_purchased"]).split()[:3])
            discount = money(r["coupon"]) or money(r["gift_certificate"])
            orders.append(
                new_order(
                    "adafruit",
                    oid,
                    date,
                    status=status(r["order_status"]),
                    total=money(r["total"]),
                    shipMethod=_adafruit_text(r["shipping_method"]),
                    summary={
                        "subtotal": money(r["subtotal"]),
                        "shipping": money(r["shipping"]),
                        "tax": money(r["tax"]),
                        "discount": discount,
                    },
                    items=[
                        new_item(
                            i["name"], **{k: v for k, v in i.items() if k != "name"}
                        )
                        for i in fetched.get(oid, {}).get("items", [])
                    ],
                )
            )
    return orders


STORES = [
    {
        "id": "amazon",
        "name": "Amazon",
        "source": "Order History.csv + Digital Content Orders.csv",
        "load": load_amazon,
    },
    {
        "id": "adafruit",
        "name": "Adafruit",
        "source": "Adafruit/order_history.csv + items.json",
        "load": load_adafruit,
    },
]


def _compact(v):
    """Drop empty/false fields; the app treats them as absent."""
    if isinstance(v, dict):
        return {k: _compact(x) for k, x in v.items() if x not in ("", False, None)}
    if isinstance(v, list):
        return [_compact(x) for x in v]
    return v


def build_data():
    stores, orders = [], []
    for store in STORES:
        name, loaded = store["name"], store["load"]()
        if not loaded:
            print(f"  {name}: no export found, skipped")
            continue
        stores.append({k: store[k] for k in ("id", "name", "source")})
        orders += loaded
        items = sum(len(o["items"]) for o in loaded)
        print(f"  {name}: {len(loaded):,} orders, {items:,} items")

    for order in orders:
        if not order["total"] and order["items"]:
            totals = [float(i["total"]) for i in order["items"] if i["total"]]
            order["total"] = f"{sum(totals):.2f}" if totals else ""
    orders.sort(key=lambda o: o["date"], reverse=True)

    data = {
        "generated": datetime.date.today().isoformat(),
        "stores": stores,
        "orders": [_compact(o) for o in orders],
    }
    os.makedirs(os.path.dirname(DATA_JSON), exist_ok=True)
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"wrote {DATA_JSON}")


def build_page():
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found: install Node.js to build the page")
    if not os.path.isdir(os.path.join(APP, "node_modules")):
        subprocess.run([npm, "ci"], cwd=APP, check=True)
    subprocess.run([npm, "run", "build"], cwd=APP, check=True)
    shutil.copyfile(os.path.join(APP, "dist", "index.html"), OUT_HTML)
    print(f"wrote {OUT_HTML}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument(
        "--data-only", action="store_true", help="write data.json, skip Vite"
    )
    args = parser.parse_args()
    build_data()
    if not args.data_only:
        build_page()


if __name__ == "__main__":
    main()
