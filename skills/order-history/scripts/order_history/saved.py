# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Saved orders: orders read from a store's order pages, kept until an export
has them (docs/design-order-pages.md).

A vendor opts in with SAVED_ORDERS = True and a saved_order(order) hook that
checks and fills its own fields (Amazon: the order and item links, the site).
Its saved orders live in <vendor>/order-pages.json:

  {"format": 1, "checked": "<ISO date and time>" or null, "orders": [...]}

Each order is in the normalized shape (model.new_order) with source
"order-page". The file is written atomically, and only under the import lock:
by `add` (new orders; a saved ID read again replaces the saved copy) and by
import (dropping the orders the new export now has). An order whose ID is in
the export is never shown, saved or not: the export wins.

`checked` is when `add` last ran for real. checked() reports the later of
that and the time the current export was imported, which is the mtime of
current/: an import writes the export into a new folder and renames it, and
a rename keeps a folder's mtime.
"""

import datetime
import decimal
import json
import os
import re

from order_history import fetching, model

FILE_NAME = "order-pages.json"
FILE_FORMAT = 1
SOURCE = "order-page"
# status reports "stale" when checked is older than this; the skill's rule
# for suggesting a refresh (M8) reads that field.
STALE_DAYS = 30

EXIT_USAGE = 2
EXIT_NO_DATA = 3
EXIT_RETRY_FREE = 20

# What an input order and item may hold. The tool fills the rest (store,
# source, the links), and refuses summary: exported Amazon orders have none,
# and a saved order must look like an exported one.
ORDER_FIELDS = ("id", "date", "currency", "total", "status", "site", "items")
ITEM_FIELDS = ("name", "asin", "qty", "unit", "total", "department")
_FILLED = ("store", "source", "url")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
QTY = re.compile(r"[1-9]\d{0,5}")


class SavedError(Exception):
    """add or a saved-orders file failed; `code` is the exit code to use."""

    def __init__(self, message, code=EXIT_USAGE):
        super().__init__(message)
        self.code = code


def supports(vendor):
    """True for a vendor that keeps saved orders."""
    return bool(getattr(vendor, "SAVED_ORDERS", False))


def path(vendor_dir):
    """The saved-orders file of a vendor folder."""
    return os.path.join(vendor_dir, FILE_NAME)


def now():
    """The current time, with the local offset (tests replace it)."""
    return datetime.datetime.now().astimezone()


# ---- the file -------------------------------------------------------------


def read_file(vendor_dir):
    """The saved-orders file as {format, checked, orders}; empty when absent.

    Raises SavedError (exit 2) for a file that can't be read or isn't one,
    which is then left as it is: nothing overwrites a file it couldn't read.
    """
    p = path(vendor_dir)
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {"format": FILE_FORMAT, "checked": None, "orders": []}
    except (OSError, ValueError) as e:
        raise SavedError(f"can't read {p} ({e}); it was left as it is") from e
    problem = _file_problem(doc)
    if problem:
        raise SavedError(f"{p} is not a saved-orders file ({problem}); left as it is")
    store = os.path.basename(os.path.normpath(vendor_dir))  # the vendor ID
    doc["orders"] = [_complete(o, store) for o in doc["orders"]]
    return doc


def _file_problem(doc):
    if not isinstance(doc, dict) or doc.get("format") != FILE_FORMAT:
        return f'no "format": {FILE_FORMAT}'
    recorded = doc.get("checked")
    if recorded is not None and _parse_time(recorded) is None:
        return '"checked" is not a date and time'
    orders = doc.get("orders")
    if not isinstance(orders, list):
        return '"orders" is not a list'
    for order in orders:
        if not (
            isinstance(order, dict)
            and isinstance(order.get("id"), str)
            and isinstance(order.get("date"), str)
            and isinstance(order.get("items"), list)
            and all(
                isinstance(i, dict) and isinstance(i.get("name"), str)
                for i in order["items"]
            )
        ):
            return "an order without an id, a date or named items"
    return None


def _complete(order, store):
    """A stored order with every field the order shape has today.

    Only id, date and the item names are required of the file, so a field
    added to model.new_order later doesn't make older files unreadable.
    """
    full = model.new_order(store, order["id"], order["date"], source=SOURCE)
    full.update(order)
    full["items"] = [{**model.new_item(i["name"]), **i} for i in order["items"]]
    return full


def write_file(vendor_dir, doc):
    """Write the saved-orders file atomically (mode 0600)."""
    fetching.write_json(path(vendor_dir), doc, indent=1, ensure_ascii=False)


def combine(orders, saved_orders):
    """orders plus copies of the saved orders whose IDs they lack."""
    known = {o["id"] for o in orders}
    extra = [json.loads(json.dumps(o)) for o in saved_orders if o["id"] not in known]
    return orders + extra


def merge(vendor_dir, orders):
    """orders plus copies of the vendor's saved orders whose IDs they lack."""
    return combine(orders, read_file(vendor_dir)["orders"])


# ---- freshness ------------------------------------------------------------


def _parse_time(text):
    if not isinstance(text, str):
        return None
    try:
        t = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def checked(vendor_dir):
    """The later of the last add and the current export's import, ISO; or None."""
    times = []
    recorded = read_file(vendor_dir)["checked"]
    if recorded:
        times.append(_parse_time(recorded))
    current = os.path.join(vendor_dir, "current")
    if os.path.isdir(current):
        mtime = os.path.getmtime(current)
        times.append(datetime.datetime.fromtimestamp(mtime).astimezone())
    if not times:
        return None
    return max(times).isoformat(timespec="seconds")


def is_stale(checked_at, at=None):
    """True when checked_at (ISO, or None) is more than STALE_DAYS before at."""
    t = _parse_time(checked_at)
    if t is None:
        return True
    return (at or now()) - t > datetime.timedelta(days=STALE_DAYS)


# ---- the input document ---------------------------------------------------


def parse(text, registry):
    """(vendor, orders) from an add input document; SavedError (exit 2) if bad.

    The document is {"store": ID, "orders": [order, ...]}; see ORDER_FIELDS
    and ITEM_FIELDS for what an order and an item may hold.
    """
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise SavedError(f"the input is not valid JSON ({e}); nothing saved") from e
    if not isinstance(doc, dict):
        raise SavedError("the input must be a JSON object; nothing saved")
    extra = sorted(set(doc) - {"store", "orders"})
    if extra:
        raise SavedError(
            "unknown field(s) in the input: " + ", ".join(extra) + "; nothing saved"
        )
    vendor = None
    for v in registry:
        if v.ID == doc.get("store"):
            vendor = v
    if vendor is None:
        known = ", ".join(v.ID for v in registry if supports(v))
        store_id = doc.get("store")
        raise SavedError(
            f"unknown store {store_id!r} (saved orders: {known}); " "nothing saved"
        )
    if not supports(vendor):
        raise SavedError(f"{vendor.NAME} doesn't keep saved orders; nothing saved")
    raw = doc.get("orders")
    if not isinstance(raw, list):
        raise SavedError('"orders" must be a list; nothing saved')
    orders, seen = [], set()
    for n, entry in enumerate(raw):
        try:
            order = _order(vendor, entry)
            vendor.saved_order(order)
        except ValueError as e:
            raise SavedError(f"orders[{n}]: {e}; nothing saved") from e
        order_id = order["id"]
        if order_id in seen:
            raise SavedError(f"order {order_id} is listed twice; nothing saved")
        seen.add(order_id)
        orders.append(order)
    return vendor, orders


def _fields(entry, allowed, what):
    if not isinstance(entry, dict):
        raise ValueError(f"{what} is not an object")
    if "summary" in entry:
        raise ValueError(
            "summary is not accepted: an exported order has none, so give the "
            "grand total as total"
        )
    filled = sorted(set(entry) & set(_FILLED))
    if filled:
        raise ValueError(", ".join(filled) + " is filled in by the tool; leave it out")
    unknown = sorted(set(entry) - set(allowed))
    if unknown:
        raise ValueError(
            f"unknown field(s) in {what}: "
            + ", ".join(unknown)
            + " (allowed: "
            + ", ".join(allowed)
            + ")"
        )


def _text(entry, key, required=False):
    value = entry.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{key} is required")
    return value


def _amount(entry, key):
    value = entry.get(key, "")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f'{key} must be an amount such as "12.34"')
    amount = model.money(str(value))
    if amount:
        try:
            finite = decimal.Decimal(amount).is_finite()
        except decimal.InvalidOperation:
            finite = False
        if not finite:
            raise ValueError(f"{key} {value!r} is not an amount")
    return amount


def _order(vendor, entry):
    _fields(entry, ORDER_FIELDS, "the order")
    order_id = _text(entry, "id", required=True)
    date = _text(entry, "date", required=True)
    try:
        if not DATE.fullmatch(date):
            raise ValueError(date)
        datetime.date.fromisoformat(date)
    except ValueError as e:
        raise ValueError(f"date {date!r} is not a YYYY-MM-DD date") from e
    items = entry.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"order {order_id} has no items")
    order = model.new_order(
        vendor.ID,
        order_id,
        date,
        status=model.status(_text(entry, "status")),
        currency=_text(entry, "currency") or "USD",
        total=_amount(entry, "total"),
        site=_text(entry, "site"),
        source=SOURCE,
    )
    for n, item in enumerate(items):
        try:
            order["items"].append(_item(item))
        except ValueError as e:
            raise ValueError(f"order {order_id}, items[{n}]: {e}") from e
    return order


def _item(entry):
    _fields(entry, ITEM_FIELDS, "the item")
    name = _text(entry, "name", required=True)
    qty = entry.get("qty", "1")
    if isinstance(qty, int) and not isinstance(qty, bool):
        qty = str(qty)
    if not isinstance(qty, str) or not QTY.fullmatch(qty.strip()):
        raise ValueError(f"qty {qty!r} is not a whole number of at least 1")
    qty = qty.strip()
    unit, total = _amount(entry, "unit"), _amount(entry, "total")
    if not total and unit:
        total = f"{decimal.Decimal(unit) * int(qty):.2f}"
    return model.new_item(
        name,
        asin=_text(entry, "asin"),
        qty=qty,
        unit=unit,
        total=total,
        department=_text(entry, "department"),
    )


# ---- add and prune --------------------------------------------------------


def add(data_dir, vendor, orders, dry_run=False, rebuild=None, at=None):
    """Save orders for vendor; returns the report. The caller holds the lock.

    The import lock for a real run, the shared one for a dry run. An order
    whose ID is in the export is skipped; a saved ID is replaced. checked is
    recorded on every real run, an empty one included. rebuild() (real runs
    only) writes the page and returns its path; its errors propagate, with
    the file already saved.
    """
    vendor_dir = os.path.join(data_dir, vendor.ID)
    current = os.path.join(vendor_dir, "current")
    if not os.path.isdir(current):
        raise SavedError(
            f"no {vendor.NAME} export is imported yet; import one before adding "
            "orders from its order pages",
            EXIT_NO_DATA,
        )
    exported = {o["id"] for o in vendor.read(current)}
    doc = read_file(vendor_dir)
    before = {o["id"] for o in doc["orders"]}
    taken = [o for o in orders if o["id"] not in exported]
    taken_ids = {o["id"] for o in taken}
    kept = [o for o in doc["orders"] if o["id"] not in taken_ids]
    after = sorted(kept + taken, key=lambda o: (o["date"], o["id"]), reverse=True)
    report = {
        "store": vendor.ID,
        "dry_run": dry_run,
        "added": [o["id"] for o in taken if o["id"] not in before],
        "replaced": [o["id"] for o in taken if o["id"] in before],
        "skipped_in_export": [o["id"] for o in orders if o["id"] in exported],
        "saved_orders": sum(1 for o in after if o["id"] not in exported),
        "checked": doc["checked"],
        "page": None,
    }
    if dry_run:
        return report
    report["checked"] = (at or now()).isoformat(timespec="seconds")
    try:
        write_file(
            vendor_dir,
            {"format": FILE_FORMAT, "checked": report["checked"], "orders": after},
        )
    except OSError as e:
        raise SavedError(
            f"can't write {path(vendor_dir)} ({e}); nothing saved", EXIT_RETRY_FREE
        ) from e
    if rebuild is not None:
        report["page"] = rebuild()
    return report


def prune(vendor_dir, export_ids, dry_run=False):
    """Drop saved orders whose IDs are in the export; the import report's part.

    {"replaced_by_export": [ids], "kept": n}. Called by import after a
    successful swap, under the import lock (or with dry_run, writing nothing).
    """
    doc = read_file(vendor_dir)
    gone = [o["id"] for o in doc["orders"] if o["id"] in export_ids]
    kept = [o for o in doc["orders"] if o["id"] not in export_ids]
    if gone and not dry_run:
        write_file(vendor_dir, {**doc, "orders": kept})
    return {"replaced_by_export": sorted(gone), "kept": len(kept)}
