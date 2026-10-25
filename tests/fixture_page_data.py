# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Print the page data for the fixture data folder, as page.py builds it.

The page's own tests (web/test/) read this, so search.ts is checked against
the same orders and the same case file as search.py.
"""

import datetime
import json
import os
import sys

import support
from order_history import page, vendors


def main():
    """Write the fixture page data to stdout as JSON."""
    loaded = [
        (v, v.load(os.path.join(support.FIXTURE_DATA, v.ID))) for v in vendors.VENDORS
    ]
    data = page.page_data(loaded, today=datetime.date(2025, 1, 1))
    json.dump(data, sys.stdout)


if __name__ == "__main__":
    main()
