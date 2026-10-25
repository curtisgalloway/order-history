# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The normalized order shape every vendor loader returns, and its helpers.

Copied from search/build.py, which keeps its own copies until M3 removes
search/. A vendor's load() returns a list of orders built with new_order()
and new_item(); finish() then fills in order totals and sorts.
"""

SENTINELS = {"", "Not Available", "Not Applicable"}

# The name shown for an item whose export row has no product name.
NO_NAME = "(no product name)"

# Terminal "everything went fine" states get no stamp. Amazon's Authorized is
# its payment term for an order still in flight.
STATUS_DISPLAY = {
    "Closed": "",
    "SUCCESS": "",
    "Shipped": "",
    "Authorized": "In progress",
}


def clean(v):
    """Strip a field and turn the exports' sentinel values into ""."""
    v = (v or "").strip()
    return "" if v in SENTINELS else v


def money(v):
    """Normalize a money field to "12.34", or "" when absent.

    Strips Excel armoring ("'-2.2'" -> "-2.20"), thousands separators
    ("1,234.56" -> "1234.56") and trailing precision ("42.0000" -> "42.00").
    A value that still isn't a number is returned as it is.
    """
    v = clean(v).strip("'").strip()
    if not v:
        return ""
    try:
        number = float(v.replace(",", ""))
    except ValueError:
        return v
    return f"{number:.2f}"


def status(v):
    """The status to show: "" for the normal terminal states."""
    v = clean(v)
    return STATUS_DISPLAY.get(v, v)


def new_order(store, order_id, date, **kw):
    """One order. Items are appended to order["items"] by the loader.

    Fields: store, id, date (YYYY-MM-DD), status ("" = normal), currency,
    total ("" = sum of item totals), digital, site, url, shipMethod,
    summary ({subtotal, shipping, tax, discount}, only when the export has
    order-level amounts), source ("export" for orders read from an export;
    reserved for orders added from other sources later), items.
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
        "source": "export",
        "items": [],
    }
    order.update(kw)
    return order


def new_item(name, **kw):
    """One item line of an order."""
    item = {
        "name": name or NO_NAME,
        "asin": "",
        "qty": "1",
        "unit": "",
        "total": "",
        "url": "",
    }
    item.update(kw)
    return item


def finish(orders):
    """Fill missing order totals from item totals; sort newest first, in place."""
    for order in orders:
        if not order["total"] and order["items"]:
            totals = [float(i["total"]) for i in order["items"] if i["total"]]
            order["total"] = f"{sum(totals):.2f}" if totals else ""
    orders.sort(key=lambda o: o["date"], reverse=True)
    return orders


def compact(v):
    """Drop empty/false fields; the page and --json treat them as absent."""
    if isinstance(v, dict):
        return {k: compact(x) for k, x in v.items() if x not in ("", False, None)}
    if isinstance(v, list):
        return [compact(x) for x in v]
    return v
