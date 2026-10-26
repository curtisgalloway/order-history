# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The vendor registry.

Each vendor is a module providing:

  ID, NAME
  SOURCE                the files it reads, for the page footer (optional)
  detect(path)          does this zip, CSV or folder hold this store's export?
                        Reads contents, never the filename.
  install(src, dest)    unpack or copy the export into the empty folder dest
  as_of(folder)         the newest order date in an export folder, or ""
  read(folder)          orders from an export folder alone (no caches)
  load(vendor_dir)      orders from <vendor_dir>/current/ with caches merged

and, optionally, compare(old, new) (vendor findings for the import report, from
two read() lists), gaps(vendor_dir, orders) (enrichment gaps for status) and
enrich(vendor_dir, opts, orders) (fill the vendor's caches for update, given
read() of current/, plus the saved orders for a vendor that keeps them; see
fetching.py).

A vendor that keeps saved orders (orders read from its order pages, added
with `order-history add` until an export has them; see saved.py) also has

  SAVED_ORDERS = True
  saved_order(order)    check and fill the vendor's own fields on an order
                        from an add input (links, site); ValueError if bad

and its load(vendor_dir, with_saved=True) appends the saved orders the export
lacks (with_saved=False: the export alone). The core then offers `add`, and
import drops saved orders the new export contains.
Adding a store means adding its module and listing it here; nothing else in
the core changes.
"""

from order_history.vendors import adafruit, amazon

VENDORS = [amazon, adafruit]


def by_id(vendor_id, vendors=None):
    """The registered vendor with this ID, or None."""
    for v in VENDORS if vendors is None else vendors:
        if v.ID == vendor_id:
            return v
    return None
