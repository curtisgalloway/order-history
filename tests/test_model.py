# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The normalized order shape and its field helpers."""

import unittest

import support  # pylint: disable=unused-import
from order_history import model


class FieldTest(unittest.TestCase):
    """clean(), money() and status()."""

    def test_clean_sentinels(self):
        for v in (None, "", "  ", "Not Available", "Not Applicable"):
            self.assertEqual(model.clean(v), "")
        self.assertEqual(model.clean("  x "), "x")

    def test_money(self):
        cases = {
            "'-2.2'": "-2.20",
            "1,234.56": "1234.56",
            "42.0000": "42.00",
            "0": "0.00",
            "Not Available": "",
            "": "",
            "n/a": "n/a",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(model.money(raw), want)

    def test_status(self):
        self.assertEqual(model.status("Closed"), "")
        self.assertEqual(model.status("SUCCESS"), "")
        self.assertEqual(model.status("Authorized"), "In progress")
        self.assertEqual(model.status("Cancelled"), "Cancelled")


class ShapeTest(unittest.TestCase):
    """new_order(), new_item(), finish() and compact()."""

    def test_source_is_reserved_as_export(self):
        self.assertEqual(model.new_order("s", "1", "2024-01-01")["source"], "export")

    def test_item_defaults(self):
        self.assertEqual(model.new_item("")["name"], "(no product name)")
        self.assertEqual(model.new_item("x")["qty"], "1")

    def test_finish_sums_items_and_sorts_newest_first(self):
        a = model.new_order("s", "a", "2024-01-01")
        a["items"] = [model.new_item("x", total="1.50"), model.new_item("y")]
        b = model.new_order("s", "b", "2025-01-01", total="9.00")
        c = model.new_order("s", "c", "2023-01-01")
        orders = model.finish([a, b, c])
        self.assertEqual([o["id"] for o in orders], ["b", "a", "c"])
        self.assertEqual(a["total"], "1.50")
        self.assertEqual(c["total"], "")

    def test_compact_drops_empty_fields(self):
        order = model.new_order("s", "1", "2024-01-01")
        order["items"] = [model.new_item("x")]
        self.assertEqual(
            model.compact(order),
            {
                "store": "s",
                "id": "1",
                "date": "2024-01-01",
                "currency": "USD",
                "source": "export",
                "items": [{"name": "x", "qty": "1"}],
            },
        )


if __name__ == "__main__":
    unittest.main()
