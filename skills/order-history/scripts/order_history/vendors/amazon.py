# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Amazon's "Request My Data" export.

Layout under the vendor folder (<data>/amazon/):

  current/Your Amazon Orders/Order History.csv           physical orders
  current/Your Amazon Orders/Digital Content Orders.csv  digital orders
  images.json                                            ASIN -> image cache

Both CSVs have one row per item; rows are grouped into orders by Order ID.
"""

import csv
import json
import os
import zipfile

from order_history import model, store

ID = "amazon"
NAME = "Amazon"

ORDERS_CSV = os.path.join("Your Amazon Orders", "Order History.csv")
DIGITAL_CSV = os.path.join("Your Amazon Orders", "Digital Content Orders.csv")
IMAGES_JSON = "images.json"


def detect(path):
    """True for a folder or zip that holds Your Amazon Orders/Order History.csv."""
    if os.path.isdir(path):
        return os.path.isfile(os.path.join(path, ORDERS_CSV))
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            return "Your Amazon Orders/Order History.csv" in z.namelist()
    return False


def install(src, dest):
    """Unpack a zip, or copy a folder, into the empty folder dest."""
    if os.path.isdir(src):
        store.copy_tree(src, dest)
    else:
        store.extract_zip(src, dest)


def _rows(path, digital):
    """Group one Amazon CSV's item rows into orders."""
    orders = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            oid = model.clean(r["Order ID"])
            if digital:
                cur = model.clean(r["Price Currency Code"]) or "USD"
                qty = model.clean(r["Quantity Ordered"])
                total, unit = model.money(r["Price"]), ""
                site = model.clean(r["Marketplace"])
            else:
                cur = model.clean(r["Currency"]) or "USD"
                qty = model.clean(r["Original Quantity"])
                total, unit = model.money(r["Total Amount"]), model.money(
                    r["Unit Price"]
                )
                site = model.clean(r["Website"])
            order = orders.get(oid)
            if order is None:
                order = orders[oid] = model.new_order(
                    ID,
                    oid,
                    model.clean(r["Order Date"])[:10],
                    status=model.status(r["Order Status"]),
                    currency=cur,
                    digital=digital,
                    site=site,
                    url=(
                        ""
                        if digital or not oid
                        else "https://www.amazon.com/gp/your-account/order-details"
                        f"?orderID={oid}"
                    ),
                )
            asin = model.clean(r["ASIN"])
            order["items"].append(
                model.new_item(
                    model.clean(r["Product Name"]),
                    asin=asin,
                    qty=qty or "1",
                    unit=unit,
                    total=total,
                    url=f"https://www.amazon.com/dp/{asin}" if asin else "",
                    # Exports from late 2026 on; absent in older ones.
                    department=model.clean(r.get("Department")),
                )
            )
    return list(orders.values())


def read(folder):
    """Orders from an export folder alone, without the image cache."""
    orders = []
    for rel, digital in ((ORDERS_CSV, False), (DIGITAL_CSV, True)):
        path = os.path.join(folder, rel)
        if os.path.exists(path):
            orders += _rows(path, digital)
    return orders


def as_of(folder):
    """The newest order date (YYYY-MM-DD) in an export folder, or ""."""
    return max((o["date"] for o in read(folder)), default="")


def load_images(vendor_dir):
    """The image cache, ASIN -> {"src": ..., "id": ...}; {} when absent."""
    path = os.path.join(vendor_dir, IMAGES_JSON)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(vendor_dir):
    """Orders from <vendor_dir>/current/, with images.json merged in."""
    orders = read(os.path.join(vendor_dir, "current"))
    images = load_images(vendor_dir)
    for order in orders:
        for item in order["items"]:
            info = images.get(item["asin"])
            if info and info["src"] == "i":
                item["image"] = info["id"]
            elif info and info["src"] in (None, "tbd"):
                # Known miss on the P/ endpoint: show the placeholder directly.
                item["noImage"] = True
    return orders


def compare(old, new):
    """Item names that changed between two exports (lists from read()).

    Newer exports have renamed some digital titles and blanked others to
    "Not Applicable". Items are matched by order ID and ASIN.
    """
    old_names = _names_by_asin(old)
    renamed, blanked = [], []
    for (order_id, asin), names in sorted(_names_by_asin(new).items()):
        for before, after in zip(old_names.get((order_id, asin), []), names):
            if before == after:
                continue
            entry = {"order": order_id, "asin": asin, "old": before, "new": after}
            (blanked if after == model.NO_NAME else renamed).append(entry)
    return {"titles_renamed": renamed, "titles_blanked": blanked}


def _names_by_asin(orders):
    names = {}
    for order in orders:
        for item in order["items"]:
            if item["asin"]:
                names.setdefault((order["id"], item["asin"]), []).append(item["name"])
    return names


def gaps(vendor_dir, orders):
    """Enrichment gaps for status: items whose ASIN has no image lookup yet."""
    images = load_images(vendor_dir)
    missing = {i["asin"] for o in orders for i in o["items"] if i["asin"] not in images}
    missing.discard("")
    return {"images_missing": len(missing)}
