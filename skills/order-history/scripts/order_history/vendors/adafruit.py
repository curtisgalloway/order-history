# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Adafruit's account order-history CSV.

Layout under the vendor folder (<data>/adafruit/):

  current/order_history.csv  one row per order, no item lines
  items.json                 order ID -> {"fetched": ..., "items": [...]}

The export writes "-" as a space: order IDs come out as "1234567 1234567890"
and dates as "2024 01 31 12:00:00". The loader puts the hyphens back.
"""

import csv
import json
import os
import re

from order_history import model

ID = "adafruit"
NAME = "Adafruit"

ORDERS_CSV = "order_history.csv"
ITEMS_JSON = "items.json"

# Columns the export has always had; detect() needs all of them.
HEADER = {
    "order_id",
    "date_purchased",
    "order_status",
    "subtotal",
    "shipping",
    "tax",
    "coupon",
    "gift_certificate",
    "total",
    "shipping_method",
}


def detect(path):
    """True for a CSV whose header has the export's columns."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f), [])
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return HEADER <= {h.strip() for h in header}


def _text(v):
    """Undo the export's mangling of shipping-method text.

    The export replaces "-" and "=" with spaces and leaves (sometimes
    truncated) HTML in the shipping method.
    """
    v = re.sub(r"<[^>]*>?", "", model.clean(v))
    return re.sub(r"\s+", " ", v).strip()


def _order_id(v):
    return "-".join(model.clean(v).split())


def _date(v):
    return "-".join(model.clean(v).split()[:3])


def _export_rows(folder):
    path = os.path.join(folder, ORDERS_CSV)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def as_of(folder):
    """The newest order date (YYYY-MM-DD) in an export folder, or ""."""
    return max((_date(r["date_purchased"]) for r in _export_rows(folder)), default="")


def load_items(vendor_dir):
    """The item cache written by the item fetcher; {} when absent."""
    path = os.path.join(vendor_dir, ITEMS_JSON)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(vendor_dir):
    """Orders from <vendor_dir>/current/, with items.json merged in."""
    fetched = load_items(vendor_dir)
    orders = []
    for r in _export_rows(os.path.join(vendor_dir, "current")):
        oid = _order_id(r["order_id"])
        discount = model.money(r["coupon"]) or model.money(r["gift_certificate"])
        orders.append(
            model.new_order(
                ID,
                oid,
                _date(r["date_purchased"]),
                status=model.status(r["order_status"]),
                total=model.money(r["total"]),
                shipMethod=_text(r["shipping_method"]),
                summary={
                    "subtotal": model.money(r["subtotal"]),
                    "shipping": model.money(r["shipping"]),
                    "tax": model.money(r["tax"]),
                    "discount": discount,
                },
                items=[
                    model.new_item(
                        i["name"], **{k: v for k, v in i.items() if k != "name"}
                    )
                    for i in fetched.get(oid, {}).get("items", [])
                ],
            )
        )
    return orders


def gaps(vendor_dir, orders):
    """Enrichment gaps for status: orders whose items haven't been fetched."""
    fetched = load_items(vendor_dir)
    return {"items_unfetched": sum(1 for o in orders if o["id"] not in fetched)}
