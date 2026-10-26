# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The Amazon and Adafruit loaders on the invented fixtures."""

import os
import tempfile
import unittest
import zipfile

import support
from order_history import model, vendors
from order_history.vendors import adafruit, amazon

AMAZON = os.path.join(support.FIXTURE_DATA, "amazon")
ADAFRUIT = os.path.join(support.FIXTURE_DATA, "adafruit")


def _by_id(orders):
    return {o["id"]: o for o in orders}


class AmazonTest(unittest.TestCase):
    """Amazon's two CSVs, grouped into orders, with images merged."""

    def setUp(self):
        self.orders = _by_id(amazon.load(AMAZON))

    def test_orders_and_items(self):
        self.assertEqual(len(self.orders), 6)
        self.assertEqual(sum(len(o["items"]) for o in self.orders.values()), 7)

    def test_embedded_newlines_do_not_split_rows(self):
        order = self.orders["111-0000001-0000001"]
        self.assertEqual(
            [i["name"] for i in order["items"]],
            ["Example Soldering Iron, 60W", "Solder Wire Spool"],
        )
        self.assertEqual(order["date"], "2024-03-05")
        self.assertEqual(order["items"][1]["qty"], "2")

    def test_money_quirks(self):
        self.assertEqual(
            self.orders["202-0000003-0000003"]["items"][0]["total"], "-2.20"
        )
        self.assertEqual(self.orders["202-0000003-0000003"]["currency"], "GBP")
        big = self.orders["111-0000002-0000002"]
        self.assertEqual(big["items"][0]["unit"], "1234.56")
        self.assertEqual(big["status"], "In progress")

    def test_sentinels_and_department(self):
        order = self.orders["111-0000004-0000004"]
        self.assertEqual(order["items"][0]["name"], "(no product name)")
        self.assertEqual(order["items"][0]["asin"], "")
        self.assertEqual(order["items"][0]["url"], "")
        self.assertEqual(order["items"][0]["department"], "")
        first = self.orders["111-0000001-0000001"]["items"][0]
        self.assertEqual(first["department"], "Tools")

    def test_digital_csv_with_bom(self):
        order = self.orders["D01-0000005-0000005"]
        self.assertTrue(order["digital"])
        self.assertEqual(order["date"], "2025-02-14")
        self.assertEqual(order["url"], "")
        self.assertEqual(order["items"][0]["total"], "7.99")
        self.assertEqual(order["status"], "")

    def test_images_merged(self):
        items = self.orders["111-0000001-0000001"]["items"]
        self.assertEqual(items[0]["image"], "TESTIMG01")
        self.assertTrue(items[1]["noImage"])
        self.assertNotIn("image", self.orders["D01-0000005-0000005"]["items"][0])

    def test_as_of_and_gaps(self):
        self.assertEqual(amazon.as_of(os.path.join(AMAZON, "current")), "2025-07-19")
        self.assertEqual(
            amazon.gaps(AMAZON, list(self.orders.values())), {"images_missing": 3}
        )

    def test_detect(self):
        current = os.path.join(AMAZON, "current")
        self.assertTrue(amazon.detect(current))
        self.assertFalse(amazon.detect(AMAZON))
        self.assertFalse(amazon.detect(os.path.join(ADAFRUIT, "current")))
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = os.path.join(tmp, "a.zip"), os.path.join(tmp, "b.zip")
            with zipfile.ZipFile(good, "w") as z:
                z.writestr("Your Amazon Orders/Order History.csv", "x")
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("other.csv", "x")
            self.assertTrue(amazon.detect(good))
            self.assertFalse(amazon.detect(bad))

    def test_no_export_loads_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(amazon.load(tmp), [])
            self.assertEqual(amazon.as_of(tmp), "")


def _order(order_id, *items):
    return {"id": order_id, "items": [{"asin": a, "name": n} for a, n in items]}


class AmazonCompareTest(unittest.TestCase):
    """Title changes between two exports, matched by order ID and ASIN."""

    def test_rename_and_blank(self):
        old = [_order("111-0000001-0000001", ("B01", "Old title"), ("B02", "Ebook"))]
        # read() turns a blanked "Not Applicable" title into model.NO_NAME.
        new = [
            _order("111-0000001-0000001", ("B01", "New title"), ("B02", model.NO_NAME))
        ]
        found = amazon.compare(old, new)
        self.assertEqual(
            [(f["old"], f["new"]) for f in found["titles_renamed"]],
            [("Old title", "New title")],
        )
        self.assertEqual(
            [(f["old"], f["new"]) for f in found["titles_blanked"]],
            [("Ebook", model.NO_NAME)],
        )

    def test_lines_sharing_an_asin_in_a_new_order_are_not_renames(self):
        # Several lines of one order can share an ASIN; a newer export may list
        # them in another order. That is not a rename.
        names = ["Cable", "Charger", "Case"]
        old = [_order("111-0000001-0000001", *(("B03", n) for n in names))]
        new = [_order("111-0000001-0000001", *(("B03", n) for n in reversed(names)))]
        self.assertEqual(
            amazon.compare(old, new), {"titles_renamed": [], "titles_blanked": []}
        )

    def test_one_changed_line_among_lines_sharing_an_asin(self):
        old = [_order("111-0000001-0000001", ("B03", "Cable"), ("B03", "Charger"))]
        new = [_order("111-0000001-0000001", ("B03", "Charger"), ("B03", "Cable, 2 m"))]
        found = amazon.compare(old, new)
        self.assertEqual(
            [(f["old"], f["new"]) for f in found["titles_renamed"]],
            [("Cable", "Cable, 2 m")],
        )


class AdafruitTest(unittest.TestCase):
    """Adafruit's order-level CSV, with items.json merged."""

    def setUp(self):
        self.orders = _by_id(adafruit.load(ADAFRUIT))

    def test_space_for_hyphen_quirk(self):
        self.assertEqual(
            sorted(self.orders), ["1000001-2000000001", "1000002-2000000002"]
        )
        self.assertEqual(self.orders["1000001-2000000001"]["date"], "2024-01-31")

    def test_amounts_and_ship_method(self):
        order = self.orders["1000002-2000000002"]
        self.assertEqual(order["total"], "1224.00")
        self.assertEqual(
            order["summary"],
            {
                "subtotal": "1234.00",
                "shipping": "0.00",
                "tax": "0.00",
                "discount": "-10.00",
            },
        )
        self.assertEqual(order["shipMethod"], "USPS Priority Mail Express")
        self.assertEqual(order["status"], "Processing")
        self.assertEqual(
            self.orders["1000001-2000000001"]["shipMethod"], "UPS Ground (1 3 days"
        )
        self.assertEqual(self.orders["1000001-2000000001"]["status"], "")

    def test_items_merged(self):
        items = self.orders["1000001-2000000001"]["items"]
        self.assertEqual([i["pid"] for i in items], ["9001", "9002"])
        self.assertEqual(items[1]["url"], "")
        self.assertEqual(self.orders["1000002-2000000002"]["items"], [])

    def test_as_of_and_gaps(self):
        self.assertEqual(
            adafruit.as_of(os.path.join(ADAFRUIT, "current")), "2025-08-09"
        )
        self.assertEqual(
            adafruit.gaps(ADAFRUIT, list(self.orders.values())),
            {"items_unfetched": 1},
        )

    def test_detect(self):
        csv_path = os.path.join(ADAFRUIT, "current", "order_history.csv")
        self.assertTrue(adafruit.detect(csv_path))
        self.assertFalse(adafruit.detect(os.path.join(ADAFRUIT, "current")))
        amazon_csv = os.path.join(
            AMAZON, "current", "Your Amazon Orders", "Order History.csv"
        )
        self.assertFalse(adafruit.detect(amazon_csv))
        self.assertFalse(adafruit.detect(os.path.join(ADAFRUIT, "items.json")))


class RegistryTest(unittest.TestCase):
    """The registry lists both vendors with the interface M1 needs."""

    def test_vendor_interface(self):
        self.assertEqual([v.ID for v in vendors.VENDORS], ["amazon", "adafruit"])
        for v in vendors.VENDORS:
            for name in ("ID", "NAME", "detect", "as_of", "load", "gaps"):
                self.assertTrue(hasattr(v, name), f"{v.ID}.{name}")
        self.assertIs(vendors.by_id("adafruit"), adafruit)
        self.assertTrue(amazon.SAVED_ORDERS)
        self.assertFalse(hasattr(adafruit, "SAVED_ORDERS"))
        self.assertIsNone(vendors.by_id("nope"))


if __name__ == "__main__":
    unittest.main()
