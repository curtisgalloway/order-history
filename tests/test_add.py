# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""`add`: saved orders from order pages, merged into the loaded list.

Every order here is invented; the export is the fixture data folder's.
"""

import datetime
import io
import json
import os
import re
from unittest import mock

import support
import test_import
from order_history import model, saved, store, vendors
from order_history.vendors import amazon

# Invented: a new order, and IDs that are in the fixture export.
NEW = "111-0000099-0000001"
NEW2 = "111-0000099-0000002"
EXPORTED = "111-0000001-0000001"
AT = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)


def order(order_id=NEW, date="2026-10-20", **kw):
    """One input order with one invented item."""
    doc = {
        "id": order_id,
        "date": date,
        "currency": "USD",
        "total": "35.67",
        "status": "In progress",
        "items": [
            {
                "name": "Example USB switch",
                "asin": "B000000000",
                "qty": "5",
                "unit": "6.99",
            }
        ],
    }
    doc.update(kw)
    return doc


def page_orders(data):
    """The orders in <data>/index.html's order-data element."""
    with open(os.path.join(data, "index.html"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(
        r'<script id="order-data" type="application/json">(.*?)</script>', text
    )
    return json.loads(m.group(1))["orders"]


class AddCase(support.IsolatedTestCase):
    """The fixture data folder and an input file to write."""

    def setUp(self):
        super().setUp()
        self.data = self.data_dir()
        self.amazon = os.path.join(self.data, "amazon")
        self.input = os.path.join(self.tmp, "orders.json")
        patcher = mock.patch.object(saved, "now", lambda: AT)
        patcher.start()
        self.addCleanup(patcher.stop)

    def add(self, *orders, store_id="amazon", flags=(), doc=None):
        """(exit code, report or None, stderr) of `add <input> --json`."""
        if doc is None:
            doc = {"store": store_id, "orders": list(orders)}
        with open(self.input, "w", encoding="utf-8") as f:
            f.write(doc if isinstance(doc, str) else json.dumps(doc))
        code, out, err = self.run_cli(
            "add", self.input, "--json", "--data-dir", self.data, *flags
        )
        return code, json.loads(out) if out else None, err

    def saved_file(self):
        path = saved.path(self.amazon)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def cli_json(self, *argv):
        code, out, err = self.run_cli(*argv, "--json", "--data-dir", self.data)
        return code, json.loads(out) if out else None, err


class AddTest(AddCase):
    """New, replaced and skipped orders, and an empty list."""

    def test_new_order_is_saved_found_and_shown(self):
        code, report, err = self.add(order())
        self.assertEqual(code, 0, err)
        self.assertEqual(
            report,
            {
                "store": "amazon",
                "dry_run": False,
                "added": [NEW],
                "replaced": [],
                "skipped_in_export": [],
                "saved_orders": 1,
                "checked": "2026-10-01T12:00:00+00:00",
                "page": os.path.join(self.data, "index.html"),
            },
        )
        doc = self.saved_file()
        self.assertEqual(doc["format"], 1)
        self.assertEqual(doc["checked"], "2026-10-01T12:00:00+00:00")
        self.assertEqual(
            doc["orders"][0],
            {
                "store": "amazon",
                "id": NEW,
                "date": "2026-10-20",
                "status": "In progress",
                "currency": "USD",
                "total": "35.67",
                "digital": False,
                "site": "Amazon.com",
                "url": amazon.ORDER_URL.format(order_id=NEW),
                "shipMethod": "",
                "summary": None,
                "source": "order-page",
                "items": [
                    {
                        "name": "Example USB switch",
                        "asin": "B000000000",
                        "qty": "5",
                        "unit": "6.99",
                        "total": "34.95",
                        "url": "https://www.amazon.com/dp/B000000000",
                        "department": "",
                    }
                ],
            },
        )
        self.assertEqual(os.stat(saved.path(self.amazon)).st_mode & 0o777, 0o600)
        code, found, _ = self.cli_json("search", "usb", "switch")
        self.assertEqual(code, 0)
        self.assertEqual([o["id"] for o in found["orders"]], [NEW])
        code, one, _ = self.cli_json("order", NEW)
        self.assertEqual((code, one["order"]["source"]), (0, "order-page"))
        self.assertIn(NEW, [o["id"] for o in page_orders(self.data)])

    def test_same_shape_as_an_exported_order(self):
        self.add(order())
        loaded = {o["id"]: o for o in amazon.load(self.amazon)}
        exported, new = loaded[EXPORTED], loaded[NEW]
        self.assertEqual(set(new), set(exported))
        image_fields = {"image", "noImage"}  # from images.json, either kind
        self.assertEqual(set(new["items"][0]), set(exported["items"][0]) - image_fields)
        self.assertIsNone(new["summary"])
        self.assertEqual(new["site"], exported["site"])
        # Compact (as the page and --json see them): no summary, no source mark
        # beyond the field itself, and the same fields as an exported order.
        on_page = {o["id"]: o for o in page_orders(self.data)}
        self.assertNotIn("summary", on_page[NEW])
        self.assertEqual(
            set(on_page[NEW]) - {"status"}, set(on_page[EXPORTED]) - {"status"}
        )

    def test_images_are_merged_over_saved_orders(self):
        # B000TEST01 has an image in images.json, B000TEST02 is a known miss.
        items = [
            {"name": "Example Iron", "asin": "B000TEST01", "unit": "1.00"},
            {"name": "Example Spool", "asin": "B000TEST02", "unit": "2.00"},
        ]
        self.add(order(items=items))
        new = {o["id"]: o for o in amazon.load(self.amazon)}[NEW]
        self.assertEqual(new["items"][0]["image"], "TESTIMG01")
        self.assertTrue(new["items"][1]["noImage"])

    def test_an_id_in_the_export_is_skipped(self):
        before = self.cli_json("order", EXPORTED)[1]
        code, report, _ = self.add(order(EXPORTED, items=[{"name": "Other"}]))
        self.assertEqual(code, 0)
        self.assertEqual(report["skipped_in_export"], [EXPORTED])
        self.assertEqual((report["added"], report["replaced"]), ([], []))
        self.assertEqual(self.saved_file()["orders"], [])
        self.assertEqual(self.cli_json("order", EXPORTED)[1], before)

    def test_a_saved_id_is_replaced(self):
        self.add(order(), order(NEW2, date="2026-10-21"))
        code, report, _ = self.add(order(status="Delivered", total="30.00"))
        self.assertEqual(code, 0)
        self.assertEqual((report["added"], report["replaced"]), ([], [NEW]))
        self.assertEqual(report["saved_orders"], 2)
        by_id = {o["id"]: o for o in self.saved_file()["orders"]}
        self.assertEqual(sorted(by_id), [NEW, NEW2])
        self.assertEqual(
            (by_id[NEW]["total"], by_id[NEW]["status"]), ("30.00", "Delivered")
        )

    def test_empty_list_only_records_checked(self):
        self.add(order())
        later = AT + datetime.timedelta(days=3)
        with mock.patch.object(saved, "now", lambda: later):
            code, report, _ = self.add()
        self.assertEqual(code, 0)
        self.assertEqual((report["added"], report["saved_orders"]), ([], 1))
        doc = self.saved_file()
        self.assertEqual(doc["checked"], later.isoformat(timespec="seconds"))
        self.assertEqual([o["id"] for o in doc["orders"]], [NEW])

    def test_an_older_file_missing_optional_fields_still_loads(self):
        # Recheck N1: only id, date and item names are required of the file.
        saved.write_file(
            self.amazon,
            {
                "format": 1,
                "checked": None,
                "orders": [
                    {"id": NEW, "date": "2026-10-20", "items": [{"name": "Old"}]}
                ],
            },
        )
        code, one, err = self.cli_json("order", NEW)
        self.assertEqual(code, 0, err)
        got = one["order"]
        self.assertEqual(
            (got["store"], got["source"], got["currency"], got["items"][0]["qty"]),
            ("amazon", "order-page", "USD", "1"),
        )

    def test_load_reads_the_saved_file_before_the_export(self):
        # Review F5: import prunes after its swap, so reading saved orders
        # first means a racing read can only see an order twice, never lose it.
        calls = []
        real_read, real_file = amazon.read, saved.read_file
        with (
            mock.patch.object(
                amazon, "read", lambda f: calls.append("export") or real_read(f)
            ),
            mock.patch.object(
                saved, "read_file", lambda d: calls.append("saved") or real_file(d)
            ),
        ):
            amazon.load(self.amazon)
        self.assertEqual(calls, ["saved", "export"])

    def test_export_wins_over_a_stale_saved_copy(self):
        # A saved copy of an exported ID (say, left by an interrupted prune).
        stale = model.new_order("amazon", EXPORTED, "2024-03-05", source="order-page")
        stale["items"].append(model.new_item("Stale Name"))
        saved.write_file(self.amazon, {"format": 1, "checked": None, "orders": [stale]})
        code, found, _ = self.cli_json("search", EXPORTED)
        self.assertEqual(code, 0)
        self.assertEqual(len(found["orders"]), 1)
        self.assertEqual(found["orders"][0]["source"], "export")
        self.assertEqual(self.cli_json("search", "stale", "name")[0], 1)

    def test_amounts_and_quantities(self):
        items = [
            {"name": "A", "qty": 3, "unit": 0.1},  # numbers are accepted
            {"name": "B", "qty": "2", "unit": "1,000.50", "total": "1999.00"},
            {"name": "C"},  # qty 1, no price
        ]
        code, _, err = self.add(order(items=items, total=""))
        self.assertEqual(code, 0, err)
        got = self.saved_file()["orders"][0]
        self.assertEqual(
            [(i["qty"], i["unit"], i["total"]) for i in got["items"]],
            [("3", "0.10", "0.30"), ("2", "1000.50", "1999.00"), ("1", "", "")],
        )
        self.assertEqual(got["total"], "")
        # As with an export, a missing order total is the items' sum.
        self.assertEqual(self.cli_json("order", NEW)[1]["order"]["total"], "1999.30")

    def test_stdin(self):
        doc = json.dumps({"store": "amazon", "orders": [order()]})
        with mock.patch("sys.stdin", io.StringIO(doc)):
            code, out, err = self.run_cli("add", "-", "--json", "--data-dir", self.data)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["added"], [NEW])

    def test_text_output(self):
        with open(self.input, "w", encoding="utf-8") as f:
            json.dump({"store": "amazon", "orders": [order(), order(EXPORTED)]}, f)
        code, out, _ = self.run_cli("add", self.input, "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "amazon: 1 added, 0 replaced, 1 already in the export; 1 saved orders",
                "page: rebuilt " + os.path.join(self.data, "index.html"),
            ],
        )
        code, out, _ = self.run_cli(
            "add", self.input, "--dry-run", "--data-dir", self.data
        )
        self.assertEqual(
            out.splitlines(),
            [
                "amazon: dry run, nothing saved: 0 added, 1 replaced, 1 already in "
                "the export"
            ],
        )


class DryRunTest(AddCase):
    """--dry-run reports and writes nothing."""

    def test_nothing_changes(self):
        self.add(order(NEW2))
        before = test_import.snapshot(self.data)
        code, report, _ = self.add(
            order(), order(NEW2), order(EXPORTED), flags=["--dry-run"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            (report["dry_run"], report["added"], report["replaced"]),
            (True, [NEW], [NEW2]),
        )
        self.assertEqual(report["skipped_in_export"], [EXPORTED])
        self.assertEqual(report["saved_orders"], 2)
        self.assertIsNone(report["page"])
        self.assertEqual(test_import.snapshot(self.data), before)

    def test_on_a_fresh_folder_creates_nothing(self):
        before = test_import.snapshot(self.data)
        self.assertEqual(self.add(order(), flags=["--dry-run"])[0], 0)
        self.assertEqual(test_import.snapshot(self.data), before)


class InvalidInputTest(AddCase):
    """Every bad input exits 2 and leaves order-pages.json as it was."""

    def test_each_invalid_input(self):
        self.add(order(NEW2))
        before = test_import.snapshot(self.data)
        item = {"name": "Example"}
        cases = {
            "not JSON": "{not json",
            "not an object": "[]",
            "unknown top-level field": {"store": "amazon", "orders": [], "x": 1},
            "unknown store": {"store": "nowhere", "orders": []},
            "no store": {"orders": []},
            "store without saved orders": {"store": "adafruit", "orders": []},
            "orders not a list": {"store": "amazon", "orders": {}},
            "missing id": [{k: v for k, v in order().items() if k != "id"}],
            "empty id": [order(" ")],
            "missing date": [{k: v for k, v in order().items() if k != "date"}],
            "date not YYYY-MM-DD": [order(date="2026-1-5")],
            "date that doesn't exist": [order(date="2026-02-30")],
            "date with a time": [order(date="2026-10-20T10:00:00Z")],
            "missing item name": [order(items=[{"asin": "B000000000"}])],
            "empty item name": [order(items=[{"name": "  "}])],
            "no items": [order(items=[])],
            "items not a list": [order(items="x")],
            "summary": [order(summary={"subtotal": "1.00"})],
            "unknown order field": [order(seller="Someone")],
            "unknown item field": [order(items=[{**item, "colour": "red"}])],
            "filled field url": [order(url="https://example.com/")],
            "filled field source": [order(source="export")],
            "filled item url": [order(items=[{**item, "url": "https://example.com/"}])],
            "qty zero": [order(items=[{**item, "qty": "0"}])],
            "qty not a number": [order(items=[{**item, "qty": "two"}])],
            "qty boolean": [order(items=[{**item, "qty": True}])],
            "unit not an amount": [order(items=[{**item, "unit": "abc"}])],
            "unit NaN": [order(items=[{**item, "unit": "nan"}])],
            "total not an amount": [order(total="free")],
            "status not a string": [order(status=3)],
            "listed twice": [order(), order()],
            "ASIN not Amazon's shape": [order(items=[{**item, "asin": "../x"}])],
            "order ID not Amazon's shape": [order("12345")],
            "order not an object": ["x"],
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                if isinstance(case, list):
                    case = {"store": "amazon", "orders": case}
                code, report, err = self.add(doc=case)
                self.assertEqual(code, 2, err)
                self.assertIsNone(report)
                self.assertIn("nothing saved", err)
                self.assertEqual(test_import.snapshot(self.data), before)

    def test_unreadable_input_file(self):
        code, out, err = self.run_cli(
            "add", os.path.join(self.tmp, "missing.json"), "--data-dir", self.data
        )
        self.assertEqual((code, out), (2, ""))
        self.assertIn("can't read", err)
        with open(self.input, "wb") as f:
            f.write(b"\xff\xfe not utf-8")
        self.assertEqual(self.run_cli("add", self.input, "--data-dir", self.data)[0], 2)

    def test_corrupt_saved_file_is_never_overwritten(self):
        path = saved.path(self.amazon)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"format": 1, "orders": [')
        with store.import_lock(self.data):
            pass  # the lock file is the only thing a refused add may create
        before = test_import.snapshot(self.data)
        code, _, err = self.add(order())
        self.assertEqual(code, 2)
        self.assertIn("left as it is", err)
        self.assertEqual(test_import.snapshot(self.data), before)
        # Reading commands say so too, rather than hiding the saved orders.
        self.assertEqual(self.cli_json("search", "usb")[0], 2)
        no_date = model.new_order("amazon", NEW, "", source="order-page")
        del no_date["date"]
        for bad in (
            json.dumps({"format": 1, "checked": None, "orders": [no_date]}),
            '{"orders": []}',
            '{"format": 1, "orders": [{"id": 1}]}',
            '{"format": 1, "checked": "yesterday", "orders": []}',
        ):
            with self.subTest(bad=bad):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(bad)
                self.assertEqual(self.add(order())[0], 2)


class ExitCodeTest(AddCase):
    """3 without a data folder or an export, 4 without a page, 20 mid-import."""

    def test_no_data_folder(self):
        self.data = os.path.join(self.tmp, "nowhere")
        self.assertEqual(self.add(order())[0], 3)

    def test_no_amazon_export(self):
        os.rename(os.path.join(self.tmp, "data"), os.path.join(self.tmp, "full"))
        self.data = self.data_dir(vendors=("adafruit",))
        code, _, err = self.add(order())
        self.assertEqual(code, 3)
        self.assertIn("no Amazon export", err)
        self.assertFalse(os.path.exists(os.path.join(self.data, "amazon")))

    def test_page_not_built_keeps_the_saved_orders(self):
        os.unlink(self.cached_shell)
        code, report, err = self.add(order())
        self.assertEqual(code, 4)
        self.assertIsNone(report)
        self.assertIn("The orders were saved; run `order-history build`", err)
        self.assertEqual([o["id"] for o in self.saved_file()["orders"]], [NEW])

    def test_import_running(self):
        self.add(order(NEW2))
        before = test_import.snapshot(self.data)
        with store.import_lock(self.data):
            for flags in ((), ("--dry-run",)):
                with self.subTest(flags=flags):
                    code, _, err = self.add(order(), flags=flags)
                    self.assertEqual(code, 20)
                    self.assertIn("another import is running", err)
        self.assertEqual(test_import.snapshot(self.data), before)

    def test_write_failure_exits_20(self):
        with mock.patch.object(
            saved.fetching, "write_json", side_effect=OSError("full")
        ):
            code, _, err = self.add(order())
        self.assertEqual(code, 20)
        self.assertIn("nothing saved", err)
        self.assertIsNone(self.saved_file())


class StatusTest(AddCase):
    """status: saved_orders, checked (the later of add and import) and stale."""

    def set_current_mtime(self, when):
        os.utime(os.path.join(self.amazon, "current"), (when.timestamp(),) * 2)

    def amazon_status(self):
        return self.cli_json("status")[1]["vendors"][0]

    def test_fields(self):
        imported = AT - datetime.timedelta(days=40)
        self.set_current_mtime(imported)
        entry = self.amazon_status()
        self.assertEqual(entry["saved_orders"], 0)
        self.assertEqual(datetime.datetime.fromisoformat(entry["checked"]), imported)
        self.assertTrue(entry["stale"])
        self.add(order(), order(EXPORTED))
        entry = self.amazon_status()
        self.assertEqual((entry["orders"], entry["saved_orders"]), (7, 1))
        self.assertEqual(entry["checked"], "2026-10-01T12:00:00+00:00")
        self.assertFalse(entry["stale"])
        self.assertEqual(entry["gaps"], {"images_missing": 4})  # B000000000 too

    def test_a_newer_import_counts_as_checked(self):
        self.add()
        imported = AT + datetime.timedelta(days=2)
        self.set_current_mtime(imported)
        entry = self.amazon_status()
        self.assertEqual(datetime.datetime.fromisoformat(entry["checked"]), imported)

    def test_adafruit_has_no_saved_fields(self):
        entry = self.cli_json("status")[1]["vendors"][1]
        self.assertEqual(entry["id"], "adafruit")
        for key in ("saved_orders", "checked", "stale"):
            self.assertNotIn(key, entry)

    def test_text(self):
        self.set_current_mtime(AT - datetime.timedelta(days=40))
        self.add(order())
        code, out, _ = self.run_cli("status", "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertIn(
            "amazon: as of 2025-07-19, 7 orders, 8 items (1 saved from order pages); "
            "images missing 4; checked 2026-10-01T12:00:00+00:00",
            out,
        )

    def test_the_30_day_boundary(self):
        checked = "2026-10-01T12:00:00+00:00"
        edge = AT + datetime.timedelta(days=saved.STALE_DAYS)
        self.assertEqual(saved.STALE_DAYS, 30)
        self.assertFalse(saved.is_stale(checked, edge))
        self.assertTrue(saved.is_stale(checked, edge + datetime.timedelta(seconds=1)))
        self.assertFalse(saved.is_stale(checked, AT))
        self.assertTrue(saved.is_stale(None, AT))
        # Another offset, same instant.
        self.assertFalse(saved.is_stale("2026-10-01T05:00:00-07:00", edge))
        with mock.patch.object(
            saved, "now", lambda: edge + datetime.timedelta(hours=1)
        ):
            self.add()  # records checked = the new now
            self.assertFalse(self.amazon_status()["stale"])


class VendorContractTest(support.IsolatedTestCase):
    """Only Amazon keeps saved orders; the hook's checks."""

    def test_capability(self):
        self.assertEqual(
            [v.ID for v in vendors.VENDORS if saved.supports(v)], ["amazon"]
        )
        self.assertTrue(callable(amazon.saved_order))

    def test_registry_without_the_vendor(self):
        data = self.data_dir()
        path = os.path.join(self.tmp, "in.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"store": "amazon", "orders": []}, f)
        registry = [v for v in vendors.VENDORS if v.ID != "amazon"]
        code, _, err = self.run_cli("add", path, "--data-dir", data, registry=registry)
        self.assertEqual(code, 2)
        self.assertIn("unknown store", err)
