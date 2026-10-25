# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""CLI exit codes, JSON shape and stdout/stderr separation."""

import json
import os
import subprocess
import sys
import types
import unittest

import support
from order_history import model


class StatusTest(support.IsolatedTestCase):
    """`status` per vendor, including a vendor with no export."""

    def test_json_reports_each_vendor_and_missing(self):
        data = self.data_dir(vendors=("adafruit",))
        code, out, err = self.run_cli("status", "--json", "--data-dir", data)
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(list(doc), ["data_dir", "vendors", "page_built"])
        self.assertEqual(doc["data_dir"], data)
        self.assertIsNone(doc["page_built"])
        self.assertEqual(
            doc["vendors"],
            [
                {"id": "amazon", "name": "Amazon", "status": "missing"},
                {
                    "id": "adafruit",
                    "name": "Adafruit",
                    "status": "ok",
                    "as_of": "2025-08-09",
                    "orders": 2,
                    "items": 2,
                    "gaps": {"items_unfetched": 1},
                },
            ],
        )

    def test_text_and_page_time(self):
        data = self.data_dir()
        with open(os.path.join(data, "index.html"), "w", encoding="utf-8") as f:
            f.write("<html></html>")
        code, out, _ = self.run_cli("status", "--data-dir", data)
        self.assertEqual(code, 0)
        self.assertIn("amazon: as of 2025-07-19, 6 orders, 7 items", out)
        self.assertIn("adafruit: as of 2025-08-09, 2 orders, 2 items", out)
        self.assertIn("page: built ", out)

    def test_env_var_selects_the_folder(self):
        os.environ["ORDER_HISTORY_DIR"] = self.data_dir()
        code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["vendors"][0]["orders"], 6)


class SearchTest(support.IsolatedTestCase):
    """`search` exit codes, JSON and text output."""

    def setUp(self):
        super().setUp()
        self.data = self.data_dir()

    def test_match_json(self):
        code, out, _ = self.run_cli(
            "search", "solder", "wire", "--json", "--data-dir", self.data
        )
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(list(doc), ["terms", "empty", "orders"])
        self.assertEqual(doc["terms"], ["solder", "wire"])
        self.assertFalse(doc["empty"])
        self.assertEqual([o["id"] for o in doc["orders"]], ["111-0000001-0000001"])
        order = doc["orders"][0]
        self.assertEqual(
            list(order)[:4], ["store", "id", "date", "currency"], "stable key order"
        )
        self.assertEqual([i["name"] for i in order["items"]], ["Solder Wire Spool"])

    def test_no_match_exits_1_with_empty_true(self):
        code, out, _ = self.run_cli("--json", "search", "zzz", "--data-dir", self.data)
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(out), {"terms": ["zzz"], "empty": True, "orders": []}
        )
        code, out, err = self.run_cli("search", "zzz", "--data-dir", self.data)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("0 matching orders", err)

    def test_text_goes_to_stdout_count_to_stderr(self):
        code, out, err = self.run_cli("search", "adafruit", "--data-dir", self.data)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("2025-08-09  adafruit  1000002-2000000002"))
        self.assertIn("(item list not in export)", lines[0])
        self.assertNotIn("matching", out)
        self.assertEqual(err.strip(), "2 matching orders")

    def test_filters(self):
        code, out, _ = self.run_cli(
            "search", "2025", "--kind", "digital", "--json", "--data-dir", self.data
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            [o["id"] for o in json.loads(out)["orders"]], ["D01-0000005-0000005"]
        )
        code, _, err = self.run_cli(
            "search", "x", "--store", "nope", "--data-dir", self.data
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown store", err)

    def test_usage_errors_exit_2(self):
        code, _, _ = self.run_cli("search", "--data-dir", self.data)
        self.assertEqual(code, 2)
        code, _, _ = self.run_cli("bogus")
        self.assertEqual(code, 2)


class TextOutputTest(support.IsolatedTestCase):
    """Text output prices and control characters."""

    def test_item_without_total_shows_no_price(self):
        order = model.new_order("widgets", "W-1", "2026-01-01", total="9.00")
        order["items"] = [
            model.new_item("Priced", total="9.00"),
            model.new_item("Unpriced"),
        ]
        registry = [_test_vendor(order)]
        data = self.data_dir(vendors=())
        os.makedirs(os.path.join(data, "widgets", "current"))
        code, out, _ = self.run_cli(
            "search", "w-1", "--data-dir", data, registry=registry
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "2026-01-01  widgets  W-1  9.00 USD  Priced",
                "2026-01-01  widgets  W-1  -  Unpriced",
            ],
        )

    def test_control_characters_are_replaced(self):
        order = model.new_order("widgets", "W-1", "2026-01-01")
        order["items"] = [model.new_item("Bad\x1b]0;title\x07Name")]
        registry = [_test_vendor(order)]
        data = self.data_dir(vendors=())
        os.makedirs(os.path.join(data, "widgets", "current"))
        code, out, _ = self.run_cli(
            "order", "W-1", "--data-dir", data, registry=registry
        )
        self.assertEqual(code, 0)
        self.assertIn("Bad?]0;title?Name", out)
        self.assertNotIn("\x1b", out)
        code, out, _ = self.run_cli(
            "order", "W-1", "--json", "--data-dir", data, registry=registry
        )
        self.assertEqual(
            json.loads(out)["order"]["items"][0]["name"], "Bad\x1b]0;title\x07Name"
        )


class OrderTest(support.IsolatedTestCase):
    """`order ID`."""

    def setUp(self):
        super().setUp()
        self.data = self.data_dir()

    def test_one_order(self):
        code, out, _ = self.run_cli(
            "order", "1000001-2000000001", "--json", "--data-dir", self.data
        )
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(list(doc), ["id", "empty", "order"])
        self.assertEqual(doc["order"]["total"], "26.55")
        self.assertEqual(len(doc["order"]["items"]), 2)
        code, out, _ = self.run_cli(
            "order", "111-0000001-0000001", "--data-dir", self.data
        )
        self.assertEqual(code, 0)
        self.assertIn("amazon order 111-0000001-0000001, 2024-03-05", out)
        self.assertIn("2 x Solder Wire Spool", out)

    def test_unknown_store_exits_2(self):
        code, _, err = self.run_cli(
            "order", "111-0000001-0000001", "--store", "nope", "--data-dir", self.data
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown store", err)

    def test_duplicate_ids(self):
        a = model.new_order("widgets", "W-1", "2026-01-01")
        b = model.new_order("widgets", "W-1", "2025-01-01", digital=True)
        other = _test_vendor(model.new_order("gadgets", "W-1", "2024-01-01"))
        other.ID, other.NAME = "gadgets", "Gadgets"
        for vid in ("widgets", "gadgets"):
            os.makedirs(os.path.join(self.data, vid, "current"))
        code, _, err = self.run_cli(
            "order", "W-1", "--data-dir", self.data, registry=[_test_vendor(a, b)]
        )
        self.assertEqual(code, 2)
        self.assertIn("2 orders have ID W-1 (widgets)", err)
        self.assertIn("order-history search W-1", err)
        registry = [_test_vendor(a), other]
        code, _, err = self.run_cli(
            "order", "W-1", "--data-dir", self.data, registry=registry
        )
        self.assertEqual(code, 2)
        self.assertIn("(gadgets, widgets); pass --store", err)
        code, out, _ = self.run_cli(
            "order",
            "W-1",
            "--store",
            "gadgets",
            "--json",
            "--data-dir",
            self.data,
            registry=registry,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["order"]["store"], "gadgets")

    def test_unknown_id_exits_1(self):
        code, out, err = self.run_cli("order", "nope", "--data-dir", self.data)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no order nope", err)
        code, out, _ = self.run_cli("order", "nope", "--json", "--data-dir", self.data)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), {"id": "nope", "empty": True, "order": None})


def _test_vendor(*orders):
    """A store defined only here: the registry is the only hook (R1)."""
    if not orders:
        order = model.new_order("widgets", "W-1", "2026-01-01")
        order["items"].append(model.new_item("Blue Widget"))
        orders = (order,)

    def load(vendor_dir):
        del vendor_dir  # the test vendor has no files
        return [dict(o, items=list(o["items"])) for o in orders]

    return types.SimpleNamespace(
        ID="widgets",
        NAME="Widgets",
        detect=lambda path: False,
        as_of=lambda folder: "2026-01-01",
        load=load,
    )


class TestVendorTest(support.IsolatedTestCase):
    """A vendor registered in a test loads, reports and searches."""

    def test_registered_vendor(self):
        data = self.data_dir()
        os.makedirs(os.path.join(data, "widgets", "current"))
        from order_history import vendors  # pylint: disable=import-outside-toplevel

        registry = vendors.VENDORS + [_test_vendor()]
        code, out, _ = self.run_cli(
            "search", "widgets", "blue", "--json", "--data-dir", data, registry=registry
        )
        self.assertEqual(code, 0)
        self.assertEqual([o["id"] for o in json.loads(out)["orders"]], ["W-1"])
        code, out, _ = self.run_cli(
            "status", "--json", "--data-dir", data, registry=registry
        )
        self.assertEqual(code, 0)
        widgets = json.loads(out)["vendors"][2]
        self.assertEqual(widgets["orders"], 1)
        self.assertNotIn("gaps", widgets)


class EntryPointTest(support.IsolatedTestCase):
    """The scripts/order-history file runs from any working directory."""

    def test_status_via_script(self):
        data = self.data_dir()
        result = subprocess.run(
            [sys.executable, support.ENTRY, "status", "--data-dir", data],
            cwd=self.tmp,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("amazon: as of 2025-07-19", result.stdout)

    def test_missing_folder_via_script(self):
        result = subprocess.run(
            [sys.executable, support.ENTRY, "status", "--data-dir", "nowhere"],
            cwd=self.tmp,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "")
        self.assertIn("order-history init", result.stderr)


if __name__ == "__main__":
    unittest.main()
