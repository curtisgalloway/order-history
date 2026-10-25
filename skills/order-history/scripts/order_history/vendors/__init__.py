# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The vendor registry.

Each vendor is a module providing ID, NAME, detect(path), as_of(folder),
load(vendor_dir) and, optionally, gaps(vendor_dir, orders). Adding a store
means adding its module and listing it here; nothing else in the core changes.
"""

from order_history.vendors import adafruit, amazon

VENDORS = [amazon, adafruit]


def by_id(vendor_id, vendors=None):
    """The registered vendor with this ID, or None."""
    for v in VENDORS if vendors is None else vendors:
        if v.ID == vendor_id:
            return v
    return None
