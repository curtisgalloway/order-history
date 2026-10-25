# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The vendor registry.

Each vendor is a module providing:

  ID, NAME
  detect(path)          does this zip, CSV or folder hold this store's export?
                        Reads contents, never the filename.
  install(src, dest)    unpack or copy the export into the empty folder dest
  as_of(folder)         the newest order date in an export folder, or ""
  read(folder)          orders from an export folder alone (no caches)
  load(vendor_dir)      orders from <vendor_dir>/current/ with caches merged

and, optionally, compare(old, new) (vendor findings for the import report, from
two read() lists) and gaps(vendor_dir, orders) (enrichment gaps for status).
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
