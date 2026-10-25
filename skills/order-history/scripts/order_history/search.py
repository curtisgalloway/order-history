# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Search with the page's matching rules (web/src/search.ts).

Every order gets a lower-cased haystack of its own fields, and every item one
of its fields. An item matches when each query term is in the order's
haystack or the item's: the order's fields count toward each of its items.
An order with no item lines matches as one row whose haystack also holds
"items not in export". Matching is a plain substring test, as on the page.
"""


def _join(values):
    return " ".join(v or "" for v in values).lower()


def order_hay(order, store_name):
    """The order-level haystack, field for field as search.ts builds it."""
    return _join(
        [
            store_name,
            order["id"],
            order["date"],
            order["status"],
            order["site"],
            order["shipMethod"],
            "digital kindle" if order["digital"] else "physical",
        ]
    )


def item_hay(item):
    """The item-level haystack, field for field as search.ts builds it."""
    return _join(
        [item.get("name"), item.get("asin"), item.get("pid"), item.get("department")]
    )


def parse_terms(query):
    """Split a query into lower-cased terms."""
    return query.lower().split()


def search(orders, terms, store_names, store=None, kind=None):
    """Orders with at least one matching item, each holding only those items.

    Orders keep their input order. An order with no item lines is returned
    with an empty item list when it matches. `store` limits the search to one
    vendor ID; `kind` is "physical", "digital" or None.
    """
    results = []
    for order in orders:
        if store and order["store"] != store:
            continue
        if kind == "digital" and not order["digital"]:
            continue
        if kind == "physical" and order["digital"]:
            continue
        hay = order_hay(order, store_names.get(order["store"], ""))
        if not order["items"]:
            row = hay + " items not in export"
            if all(t in row for t in terms):
                results.append(dict(order, items=[]))
            continue
        hits = [
            item
            for item in order["items"]
            if all(t in hay + " " + item_hay(item) for t in terms)
        ]
        if hits:
            results.append(dict(order, items=hits))
    return results
