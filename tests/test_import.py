# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""`import`: detection, staging, the comparison report, archiving and rollback.

Every export here is invented and written into a temporary folder by the test.
"""

import csv
import datetime
import json
import os
import shutil
import stat
import types
import unittest
import warnings
import zipfile
from unittest import mock

import support
from order_history import store, vendors

# Invented order IDs and products.
P1, P2, P3 = "111-0000010-0000001", "111-0000010-0000002", "111-0000010-0000003"
D1, D2 = "D01-0000010-0000001", "D01-0000010-0000002"

PHYSICAL_HEADER = [
    "Website",
    "Order ID",
    "Order Date",
    "Currency",
    "Unit Price",
    "Total Amount",
    "Original Quantity",
    "ASIN",
    "Order Status",
    "Shipping Address",
    "Ship Date",
    "Product Name",
]
DIGITAL_HEADER = [
    "Order Date",
    "Order ID",
    "Product Name",
    "ASIN",
    "Price",
    "Price Currency Code",
    "Marketplace",
    "Quantity Ordered",
    "Order Status",
]
ADAFRUIT_HEADER = (
    "order_id,date_purchased,order_status,subtotal,shipping,tax,coupon,"
    "gift_certificate,total,refund,shipping_method"
)

# (order ID, date, ASIN, name, total) per item row.
OLD_PHYSICAL = [
    (P1, "2025-01-10", "B0TESTA001", "Example Widget", "5.00"),
    (P2, "2025-02-01", "B0TESTB001", "Example Cable", "3.00"),
]
OLD_DIGITAL = [
    (D1, "2025-01-05", "B0DIGI0001", "Book One", "4.99"),
    (D2, "2025-01-06", "B0DIGI0002", "Book Two", "2.99"),
]
NEW_PHYSICAL = [
    (P1, "2025-01-10", "B0TESTA001", "Example Widget", "5.00"),
    (P1, "2025-01-10", "B0TESTF001", "Example Spare Part", "1.00"),
    (P3, "2025-03-01", "B0TESTE001", "Example Lamp", "20.00"),
]
NEW_DIGITAL = [
    (D1, "2025-01-05", "B0DIGI0001", "Book One (Revised Edition)", "4.99"),
    (D2, "2025-01-06", "B0DIGI0002", "Not Applicable", "2.99"),
]


def write_amazon(folder, physical, digital):
    """An Amazon export folder with the two order CSVs."""
    orders = os.path.join(folder, "Your Amazon Orders")
    os.makedirs(orders)
    with open(
        os.path.join(orders, "Order History.csv"), "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(PHYSICAL_HEADER)
        for oid, date, asin, name, total in physical:
            w.writerow(
                ["Amazon.com", oid, date + "T10:00:00Z", "USD", total, total, "1"]
                + [asin, "Closed", "Test Person\n1 Example Street", "", name]
            )
    with open(
        os.path.join(orders, "Digital Content Orders.csv"),
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(DIGITAL_HEADER)
        for oid, date, asin, name, price in digital:
            w.writerow(
                [date + "T10:00:00Z", oid, name, asin, price, "USD", "Amazon.com"]
                + ["1", "SUCCESS"]
            )
    return folder


def zip_folder(folder, zip_path, extra=()):
    """Zip folder's contents; extra is [(ZipInfo or name, bytes)] added after."""
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(folder):
            for name in sorted(files):
                path = os.path.join(root, name)
                z.write(path, os.path.relpath(path, folder))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # duplicate names, on purpose
            for info, data in extra:
                z.writestr(info, data)
    return zip_path


def write_adafruit(path, rows):
    """An Adafruit CSV; rows are (order number, date YYYY-MM-DD, total)."""
    lines = [ADAFRUIT_HEADER]
    for number, date, total in rows:
        number, date = number.replace("-", " "), date.replace("-", " ")
        lines.append(
            f"{number},{date} 12:00:00,Shipped,"
            f"{total},0.00,0.00,,,{total},0.00,UPS Ground"
        )
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    return path


def snapshot(root):
    """Every path under root with its type, mode and (for files) bytes."""
    state = {}
    for dirpath, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            content = None
            if stat.S_ISREG(st.st_mode):
                with open(path, "rb") as f:
                    content = f.read()
            state[os.path.relpath(path, root)] = (st.st_mode, content)
    return state


class ImportCase(support.IsolatedTestCase):
    """A data folder plus invented old and new Amazon exports."""

    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.tmp, "data")
        os.mkdir(self.data, 0o700)
        self.src = os.path.join(self.tmp, "downloads")
        os.mkdir(self.src)
        self.old_dir = write_amazon(
            os.path.join(self.src, "old"), OLD_PHYSICAL, OLD_DIGITAL
        )
        self.new_dir = write_amazon(
            os.path.join(self.src, "new"), NEW_PHYSICAL, NEW_DIGITAL
        )
        self.old_zip = zip_folder(self.old_dir, os.path.join(self.src, "old.zip"))
        self.new_zip = zip_folder(self.new_dir, os.path.join(self.src, "new.zip"))
        self.amazon = os.path.join(self.data, "amazon")
        self.current = os.path.join(self.amazon, "current")

    def import_json(self, *argv, registry=None):
        """(exit code, report or None, stderr) of `import ... --json`."""
        code, out, err = self.run_cli(
            "import", *argv, "--json", "--data-dir", self.data, registry=registry
        )
        return code, json.loads(out) if out else None, err

    def assert_current_is(self, folder):
        self.assertEqual(snapshot(self.current), snapshot(folder))

    def assert_no_staging(self):
        self.assertEqual(store.leftover_staging(self.amazon), [])


class FirstImportTest(ImportCase):
    """An empty data folder: everything is added."""

    def test_zip_into_empty_folder(self):
        code, report, err = self.import_json(self.old_zip)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["action"], "imported")
        self.assertEqual(report["store"], "amazon")
        self.assertEqual(report["as_of"], {"old": None, "new": "2025-02-01"})
        self.assertIsNone(report["archived_to"])
        self.assertEqual(
            report["orders"],
            {"before": 0, "after": 4, "added": [P1, P2, D1, D2], "removed": []},
        )
        self.assertEqual(len(report["items"]["added"]), 4)
        self.assertEqual(report["items"]["removed"], [])
        self.assertEqual(
            report["findings"], {"titles_renamed": [], "titles_blanked": []}
        )
        self.assert_current_is(self.old_dir)
        self.assertFalse(os.path.exists(os.path.join(self.amazon, "archive")))
        self.assert_no_staging()
        code, out, _ = self.run_cli("status", "--json", "--data-dir", self.data)
        amazon = json.loads(out)["vendors"][0]
        self.assertEqual((code, amazon["orders"], amazon["items"]), (0, 4, 4))

    def test_directory(self):
        code, report, err = self.import_json(self.new_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["orders"]["after"], 4)
        self.assert_current_is(self.new_dir)

    def test_text_output(self):
        self.run_cli("import", self.old_zip, "--data-dir", self.data)
        code, out, _ = self.run_cli("import", self.new_zip, "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "amazon: imported export as of 2025-03-01; current one as of "
                "2025-02-01",
                "  orders: 4 (was 4), 1 added, 1 removed",
                "  items: 5 (was 4), 2 added, 1 removed",
                "  titles renamed: 1",
                "  titles blanked: 1",
                "  previous export archived to "
                + os.path.join("amazon", "archive", "2025-02-01"),
            ],
        )


class NewerImportTest(ImportCase):
    """A newer export archives the old one and reports the exact differences."""

    def test_archives_and_reports(self):
        self.assertEqual(self.import_json(self.old_zip)[0], 0)
        code, report, err = self.import_json(self.new_zip)
        self.assertEqual(code, 0, err)
        archived = os.path.join("amazon", "archive", "2025-02-01")
        self.assertEqual(report["archived_to"], archived)
        self.assertEqual(report["as_of"], {"old": "2025-02-01", "new": "2025-03-01"})
        self.assertEqual(
            report["orders"],
            {"before": 4, "after": 4, "added": [P3], "removed": [P2]},
        )
        self.assertEqual(
            report["items"],
            {
                "before": 4,
                "after": 5,
                "added": [
                    {"order": P1, "asin": "B0TESTF001", "name": "Example Spare Part"},
                    {"order": P3, "asin": "B0TESTE001", "name": "Example Lamp"},
                ],
                "removed": [
                    {"order": P2, "asin": "B0TESTB001", "name": "Example Cable"}
                ],
            },
        )
        self.assertEqual(
            report["findings"],
            {
                "titles_renamed": [
                    {
                        "order": D1,
                        "asin": "B0DIGI0001",
                        "old": "Book One",
                        "new": "Book One (Revised Edition)",
                    }
                ],
                "titles_blanked": [
                    {
                        "order": D2,
                        "asin": "B0DIGI0002",
                        "old": "Book Two",
                        "new": "(no product name)",
                    }
                ],
            },
        )
        self.assert_current_is(self.new_dir)
        self.assertEqual(
            snapshot(os.path.join(self.data, archived)), snapshot(self.old_dir)
        )
        self.assert_no_staging()

    def test_archive_name_taken_adds_the_time(self):
        now = datetime.datetime(2026, 1, 2, 3, 4, 5)
        for _ in range(3):  # the same export three times: same as_of each time
            store.import_export(self.data, self.old_zip, vendors.VENDORS, now=now)
        self.assertEqual(
            sorted(os.listdir(os.path.join(self.amazon, "archive"))),
            ["2025-02-01", "2025-02-01T030405"],
        )
        store.import_export(self.data, self.old_zip, vendors.VENDORS, now=now)
        self.assertIn(
            "2025-02-01T030405-2", os.listdir(os.path.join(self.amazon, "archive"))
        )

    def test_never_deletes_an_archive(self):
        self.import_json(self.old_zip)
        self.import_json(self.new_zip)
        archive = os.path.join(self.amazon, "archive")
        before = snapshot(archive)
        self.import_json(self.new_zip)  # archives the new one alongside
        after = snapshot(archive)
        self.assertEqual({k: after[k] for k in before}, before)


class DryRunTest(ImportCase):
    """--dry-run reports and leaves the data folder byte-for-byte unchanged."""

    def test_empty_folder(self):
        before = snapshot(self.data)
        code, report, _ = self.import_json(self.new_zip, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(report["action"], "dry_run")
        self.assertEqual(report["orders"]["added"], [P1, P3, D1, D2])
        self.assertEqual(snapshot(self.data), before)
        self.assertEqual(os.listdir(self.data), [])

    def test_with_current(self):
        self.import_json(self.old_zip)
        before = snapshot(self.data)
        code, report, _ = self.import_json(self.new_zip, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(report["orders"]["added"], [P3])
        self.assertEqual(len(report["findings"]["titles_renamed"]), 1)
        self.assertIsNone(report["archived_to"])
        self.assertEqual(snapshot(self.data), before)

    def test_leaves_leftover_staging_alone(self):
        os.makedirs(os.path.join(self.amazon, ".staging-x"))
        before = snapshot(self.data)
        self.import_json(self.old_zip, "--dry-run")
        self.assertEqual(snapshot(self.data), before)


class OlderExportTest(ImportCase):
    """An older export exits 30 without --force, and imports with it."""

    def test_refused_then_forced(self):
        self.import_json(self.new_zip)
        before = snapshot(self.data)
        code, report, err = self.import_json(self.old_zip)
        self.assertEqual(code, 30)
        self.assertIn("--force", err)
        self.assertEqual(report["action"], "refused_older")
        self.assertEqual(report["as_of"], {"old": "2025-03-01", "new": "2025-02-01"})
        self.assertEqual(snapshot(self.data), before)
        code, report, err = self.import_json(self.old_zip, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual(report["action"], "imported")
        self.assertEqual(
            report["archived_to"], os.path.join("amazon", "archive", "2025-03-01")
        )
        self.assert_current_is(self.old_dir)


class DetectionTest(ImportCase):
    """A file no vendor claims, or that two claim, exits 2 and changes nothing."""

    def test_unrecognized(self):
        path = os.path.join(self.src, "notes.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not an export\n")
        before = snapshot(self.data)
        for target in (path, self.src, os.path.join(self.src, "missing.zip")):
            code, report, err = self.import_json(target)
            self.assertEqual((code, report), (2, None), target)
            self.assertIn("nothing changed" if "missing" not in target else "", err)
        self.assertEqual(snapshot(self.data), before)

    def test_ambiguous(self):
        greedy = types.SimpleNamespace(
            ID="greedy", NAME="Greedy", detect=lambda path: True
        )
        before = snapshot(self.data)
        code, report, err = self.import_json(
            self.old_zip, registry=vendors.VENDORS + [greedy]
        )
        self.assertEqual((code, report), (2, None))
        self.assertIn("Amazon, Greedy", err)
        self.assertEqual(snapshot(self.data), before)

    def test_not_a_data_folder(self):
        code, _, err = self.run_cli(
            "import", self.old_zip, "--data-dir", os.path.join(self.tmp, "nowhere")
        )
        self.assertEqual(code, 3)
        self.assertIn("order-history init", err)

    def test_unreadable_zip_exits_2(self):
        bad = os.path.join(self.src, "bad.zip")
        zip_folder(
            self.old_dir,
            bad,
            extra=[("Your Amazon Orders/Order History.csv", b"\xff\xfe not csv")],
        )
        # The duplicate name is refused (30) before the bad bytes are read; a
        # zip that only holds unreadable bytes can't be read (2).
        self.assertEqual(self.import_json(bad)[0], 30)
        only_bad = os.path.join(self.src, "only-bad.zip")
        with zipfile.ZipFile(only_bad, "w") as z:
            z.writestr("Your Amazon Orders/Order History.csv", b"\xff\xfe\x00 not csv")
        code, _, err = self.import_json(only_bad)
        self.assertEqual(code, 2, err)
        self.assertIn("can't read", err)
        self.assertFalse(os.path.exists(self.current))
        self.assert_no_staging()


class ZipSafetyTest(ImportCase):
    """Unsafe zip members exit 30, and nothing is written outside staging."""

    def assert_refused(self, info, data=b"x"):
        evil = zip_folder(
            self.old_dir, os.path.join(self.src, "evil.zip"), extra=[(info, data)]
        )
        self.import_json(self.old_zip)
        before = snapshot(self.data)
        downloads = snapshot(self.src)
        code, report, err = self.import_json(evil)
        self.assertEqual((code, report), (30, None), err)
        self.assertEqual(snapshot(self.data), before)
        self.assertEqual(snapshot(self.src), downloads)
        for _, _, files in os.walk(self.tmp):
            self.assertNotIn("evil-x", files)
        return err

    def test_parent_component(self):
        self.assertIn("leads outside", self.assert_refused("../evil-x"))
        self.assert_refused("Your Amazon Orders/../../evil-x")

    def test_backslash_parent_component(self):
        self.assert_refused("..\\evil-x")

    def test_absolute_paths(self):
        self.assertIn("absolute", self.assert_refused("/tmp/evil-x"))
        self.assert_refused("C:/evil-x")

    def test_symlink(self):
        info = zipfile.ZipInfo("Your Amazon Orders/evil-x")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assertIn("symbolic link", self.assert_refused(info, b"/etc/passwd"))

    def test_duplicate_member(self):
        self.assertIn(
            "appears twice",
            self.assert_refused("Your Amazon Orders/Order History.csv", b"x"),
        )

    def test_check_zip_refuses_before_writing(self):
        evil = zip_folder(
            self.old_dir, os.path.join(self.src, "evil.zip"), extra=[("../e", b"x")]
        )
        dest = os.path.join(self.tmp, "dest")
        os.mkdir(dest)
        with self.assertRaises(store.StoreError) as ctx:
            store.extract_zip(evil, dest)
        self.assertEqual(ctx.exception.code, 30)
        self.assertEqual(os.listdir(dest), [])


class FolderSafetyTest(ImportCase):
    """An export folder holding a symbolic link exits 30 and copies nothing."""

    def test_symlink_in_folder(self):
        os.symlink("/etc/hosts", os.path.join(self.old_dir, "Your Amazon Orders", "x"))
        code, report, err = self.import_json(self.old_dir)
        self.assertEqual((code, report), (30, None))
        self.assertIn("symbolic link", err)
        self.assertFalse(os.path.exists(self.current))
        self.assert_no_staging()

    def test_folder_holding_the_data_folder(self):
        write_amazon(self.tmp, OLD_PHYSICAL, OLD_DIGITAL)
        code, _, err = self.import_json(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("contains the data folder", err)


class SwappedForALinkTest(ImportCase):
    """A file that becomes a link after the first walk is still refused."""

    def test_open_regular_refuses_a_link(self):
        link = os.path.join(self.tmp, "link")
        os.symlink(os.path.join(self.old_dir, "Your Amazon Orders"), link)
        with self.assertRaises(store.StoreError) as ctx:
            store._open_regular(link)  # pylint: disable=protected-access
        self.assertEqual(ctx.exception.code, 30)


class CraftedDateTest(ImportCase):
    """An export date that looks like a path can't choose the archive folder."""

    def test_path_like_as_of_archives_as_undated(self):
        for date in ("../../../x", "/tmp/abcde"):
            with self.subTest(date=date):
                data = os.path.join(self.tmp, "data-" + str(len(os.listdir(self.tmp))))
                os.mkdir(data)
                crafted = write_amazon(
                    os.path.join(data + "-src"),
                    [(P1, date, "B0TESTA001", "Example Widget", "5.00")],
                    [],
                )
                store.import_export(data, crafted, vendors.VENDORS)
                report = store.import_export(data, self.new_zip, vendors.VENDORS)
                self.assertEqual(
                    report["archived_to"], os.path.join("amazon", "archive", "undated")
                )
                self.assertEqual(
                    snapshot(os.path.join(data, report["archived_to"])),
                    snapshot(crafted),
                )
        for _, _, files in os.walk(self.tmp):
            self.assertNotIn("x", files)
        self.assertFalse(os.path.exists("/tmp/abcde"))


class RollbackTest(ImportCase):
    """A failure after the archive step leaves the previous current/ in place."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.import_json(self.old_zip)[0], 0)
        self.before = snapshot(self.data)

    def _rename_failing(self, fails):
        real = os.rename

        def rename(src, dst):
            if fails(src, dst):
                raise OSError(5, "injected failure")
            return real(src, dst)

        return mock.patch.object(store.os, "rename", side_effect=rename)

    def test_install_rename_fails(self):
        def staging_to_current(src, dst):
            return dst == self.current and ".staging-" in src

        with self._rename_failing(staging_to_current):
            code, report, err = self.import_json(self.new_zip)
        self.assertEqual((code, report), (20, None))
        self.assertIn("previous export is current again", err)
        self.assertEqual(snapshot(self.data), self.before)

    def test_rebuild_fails(self):
        def rebuild():
            self.assert_current_is(self.new_dir)  # called after the swap
            raise RuntimeError("injected rebuild failure")

        with self.assertRaises(store.StoreError) as ctx:
            store.import_export(
                self.data, self.new_zip, vendors.VENDORS, rebuild=rebuild
            )
        self.assertEqual(ctx.exception.code, 20)
        self.assertIn("rebuild", str(ctx.exception))
        self.assertEqual(snapshot(self.data), self.before)

    def test_interrupt_during_rebuild_rolls_back(self):
        def rebuild():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            store.import_export(
                self.data, self.new_zip, vendors.VENDORS, rebuild=rebuild
            )
        self.assertEqual(snapshot(self.data), self.before)

    def test_archive_rename_fails(self):
        with self._rename_failing(lambda s, d: s == self.current):
            code, _, err = self.import_json(self.new_zip)
        self.assertEqual(code, 20)
        self.assertIn("can't archive", err)
        self.assertEqual(snapshot(self.data), self.before)

    def test_rollback_fails_exits_21_and_deletes_nothing(self):
        archive = os.path.join(self.amazon, "archive", "2025-02-01")

        def to_current(src, dst):  # both the install and its undo fail
            del src
            return dst == self.current

        with self._rename_failing(to_current):
            code, _, err = self.import_json(self.new_zip)
        self.assertEqual(code, 21)
        self.assertIn(archive, err)
        self.assertIn("Nothing was deleted", err)
        self.assertEqual(snapshot(archive), snapshot(self.old_dir))
        (leftover,) = store.leftover_staging(self.amazon)
        self.assertEqual(
            snapshot(os.path.join(self.amazon, leftover)), snapshot(self.new_dir)
        )
        code, out, _ = self.run_cli("status", "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertIn("amazon: 1 staging folder(s) left by an interrupted import", out)
        self.assertIn("an import failed and couldn't undo itself", out)
        # The next import stops rather than removing the kept staging folder.
        kept = snapshot(self.amazon)
        code, _, err = self.import_json(self.new_zip)
        self.assertEqual(code, 21)
        self.assertIn(store.RECONCILE_NAME, err)
        self.assertEqual(snapshot(self.amazon), kept)
        # Once the user has put things right and deleted the note, imports resume.
        os.rename(archive, self.current)
        os.unlink(os.path.join(self.amazon, store.RECONCILE_NAME))
        code, report, err = self.import_json(self.new_zip)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["removed_staging"], [leftover])

    def test_marker_write_fails_too(self):
        def to_current(src, dst):
            del src
            return dst == self.current

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path).endswith(store.RECONCILE_NAME):
                raise OSError(28, "injected: no space left")
            return real_open(path, *args, **kwargs)

        with (
            self._rename_failing(to_current),
            mock.patch("builtins.open", side_effect=fake_open),
        ):
            code, _, err = self.import_json(self.new_zip)
        self.assertEqual(code, 21)
        self.assertIn("don't run another import", err)
        self.assertEqual(len(store.leftover_staging(self.amazon)), 1)

    def test_first_import_rebuild_fails_says_nothing_is_installed(self):
        empty = os.path.join(self.tmp, "empty-data")
        os.mkdir(empty)

        def rebuild():
            raise RuntimeError("injected")

        with self.assertRaises(store.StoreError) as ctx:
            store.import_export(empty, self.new_zip, vendors.VENDORS, rebuild=rebuild)
        self.assertIn("no export is installed", str(ctx.exception))
        self.assertEqual(os.listdir(os.path.join(empty, "amazon")), [])

    def test_cleanup_failure_keeps_the_real_error(self):
        evil = zip_folder(
            self.old_dir, os.path.join(self.src, "evil.zip"), extra=[("../e", b"x")]
        )
        with mock.patch.object(store.shutil, "rmtree", side_effect=OSError("busy")):
            code, _, err = self.import_json(evil)
        self.assertEqual(code, 30, err)
        self.assertIn("leads outside", err)


class LeftoverStagingTest(ImportCase):
    """`status` reports a leftover staging folder; the next import removes it."""

    def test_reported_then_removed(self):
        self.import_json(self.old_zip)
        leftover = os.path.join(self.amazon, ".staging-20260101T000000-abc")
        os.makedirs(os.path.join(leftover, "Your Amazon Orders"))
        code, out, _ = self.run_cli("status", "--json", "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out)["vendors"][0]["leftover_staging"],
            [".staging-20260101T000000-abc"],
        )
        code, report, _ = self.import_json(self.new_zip)
        self.assertEqual(code, 0)
        self.assertEqual(report["removed_staging"], [".staging-20260101T000000-abc"])
        self.assertFalse(os.path.exists(leftover))

    def test_a_symlink_named_like_staging_is_left_alone(self):
        target = os.path.join(self.tmp, "keep")
        os.mkdir(target)
        os.makedirs(self.amazon)
        os.symlink(target, os.path.join(self.amazon, ".staging-link"))
        self.assertEqual(self.import_json(self.old_zip)[0], 0)
        self.assertTrue(os.path.isdir(target))
        self.assertTrue(os.path.islink(os.path.join(self.amazon, ".staging-link")))


@unittest.skipIf(store.fcntl is None, "no fcntl on this platform")
class LockTest(ImportCase):
    """A second import while one holds the lock exits 20 and changes nothing."""

    def test_busy(self):
        fd = os.open(os.path.join(self.data, store.LOCK_NAME), os.O_RDWR | os.O_CREAT)
        self.addCleanup(os.close, fd)
        store.fcntl.flock(fd, store.fcntl.LOCK_EX)
        code, _, err = self.import_json(self.old_zip)
        self.assertEqual(code, 20)
        self.assertIn("another import is running", err)
        self.assertFalse(os.path.exists(self.amazon) and os.listdir(self.amazon))

    def test_status_and_dry_run_while_an_import_runs(self):
        self.assertEqual(self.import_json(self.old_zip)[0], 0)
        live = os.path.join(self.amazon, ".staging-live")
        os.mkdir(live)
        fd = os.open(os.path.join(self.data, store.LOCK_NAME), os.O_RDWR)
        self.addCleanup(os.close, fd)
        store.fcntl.flock(fd, store.fcntl.LOCK_EX)
        code, out, _ = self.run_cli("status", "--json", "--data-dir", self.data)
        doc = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(doc["import_running"])
        self.assertNotIn("leftover_staging", doc["vendors"][0])
        before = snapshot(self.data)
        code, _, err = self.import_json(self.new_zip, "--dry-run")
        self.assertEqual(code, 20)
        self.assertIn("another import is running", err)
        self.assertEqual(snapshot(self.data), before)


class AdafruitImportTest(ImportCase):
    """Adafruit's export is a CSV."""

    def test_csv_then_newer(self):
        old = write_adafruit(
            os.path.join(self.src, "a1.csv"),
            [("1000001-2000000001", "2024-01-31", "9.00")],
        )
        new = write_adafruit(
            os.path.join(self.src, "a2.csv"),
            [
                ("1000001-2000000001", "2024-01-31", "9.00"),
                ("1000002-2000000002", "2025-08-09", "12.00"),
            ],
        )
        code, report, err = self.import_json(old)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["store"], "adafruit")
        self.assertEqual(report["orders"]["added"], ["1000001-2000000001"])
        code, report, err = self.import_json(new)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["orders"]["added"], ["1000002-2000000002"])
        self.assertEqual(report["items"]["after"], 0)  # item lines come from M4
        self.assertEqual(report["findings"], {})
        self.assertEqual(
            report["archived_to"], os.path.join("adafruit", "archive", "2024-01-31")
        )
        with (
            open(
                os.path.join(self.data, "adafruit", "current", "order_history.csv"),
                "rb",
            ) as f,
            open(new, "rb") as g,
        ):
            self.assertEqual(f.read(), g.read())

    def test_folder_is_not_an_adafruit_export(self):
        folder = os.path.join(self.src, "adafruit-folder")
        os.mkdir(folder)
        write_adafruit(os.path.join(folder, "order_history.csv"), [])
        self.assertEqual(self.import_json(folder)[0], 2)


def _widgets_vendor():
    """A store defined only in this test: the registry is the only hook (R1)."""
    from order_history import model  # pylint: disable=import-outside-toplevel

    def detect(path):
        if not os.path.isfile(path):
            return False
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readline() == "WIDGETS\n"

    def install(src, dest):
        shutil.copyfile(src, os.path.join(dest, "widgets.txt"))

    def read(folder):
        orders = []
        path = os.path.join(folder, "widgets.txt")
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines()[1:]:
                oid, date, name = line.split(",")
                order = model.new_order("widgets", oid, date)
                order["items"].append(model.new_item(name))
                orders.append(order)
        return orders

    return types.SimpleNamespace(
        ID="widgets",
        NAME="Widgets",
        detect=detect,
        install=install,
        read=read,
        as_of=lambda folder: max(o["date"] for o in read(folder)),
        load=lambda vendor_dir: read(os.path.join(vendor_dir, "current")),
    )


class TestVendorImportTest(ImportCase):
    """A vendor registered only in a test imports and searches (R1)."""

    def test_import_and_search(self):
        path = os.path.join(self.src, "widgets.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("WIDGETS\nW-1,2026-01-01,Blue Widget\n")
        registry = vendors.VENDORS + [_widgets_vendor()]
        code, report, err = self.import_json(path, registry=registry)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["orders"]["added"], ["W-1"])
        code, out, _ = self.run_cli(
            "search", "blue", "--json", "--data-dir", self.data, registry=registry
        )
        self.assertEqual(
            (code, [o["id"] for o in json.loads(out)["orders"]]), (0, ["W-1"])
        )


if __name__ == "__main__":
    unittest.main()
