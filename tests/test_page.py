# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The page (design R7): the three shell sources, filling, escaping, exit 4.

No test here runs the real npm or touches the network. Set
ORDER_HISTORY_TEST_SHELL to a built shell (web/dist/index.html) to also run the
injection test against the real one; CI's page job does.
"""

import datetime
import html.parser
import json
import os
import re
import stat
import subprocess
import unittest
from unittest import mock

import support
import test_import
from order_history import __version__, page, store, vendors

REAL_SHELL = os.environ.get("ORDER_HISTORY_TEST_SHELL")
# Read before IsolatedTestCase patches it out.
real_download = page.download
FIXTURE_AMAZON = os.path.join(support.FIXTURE_DATA, "amazon", "current")
NASTY = 'Probe </script><script>alert("x")</script> <!-- <script> </SCRIPT >'


class _Scripts(html.parser.HTMLParser):
    """Every <script> element's attributes and text, split as a browser would."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts, self._open = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._open = [dict(attrs), ""]

    def handle_data(self, data):
        if self._open is not None:
            self._open[1] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._open is not None:
            self.scripts.append(tuple(self._open))
            self._open = None


def scripts_of(text):
    """[(attrs, text)] for every script element in the page text."""
    parser = _Scripts()
    parser.feed(text)
    parser.close()
    return parser.scripts


def page_data_of(text):
    """The parsed JSON in a built page's order-data element."""
    found = [s for a, s in scripts_of(text) if a.get("id") == "order-data"]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} order-data elements")
    return json.loads(found[0])


def _no_npm_path(test):
    """Point PATH at an empty folder, so neither node nor npm can be found."""
    empty = os.path.join(test.tmp, "empty-path")
    os.makedirs(empty, exist_ok=True)
    patcher = mock.patch.dict(os.environ, {"PATH": empty})
    patcher.start()
    test.addCleanup(patcher.stop)


def _fake_web(test, shell_text, fail=False):
    """A web/ folder and an `npm` on PATH that 'builds' shell_text into dist/."""
    web = os.path.join(test.tmp, "web")
    os.makedirs(os.path.join(web, "node_modules"))
    with open(os.path.join(web, "package.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    with open(os.path.join(test.tmp, "shell-src.html"), "w", encoding="utf-8") as f:
        f.write(shell_text)
    bin_dir = os.path.join(test.tmp, "bin")
    os.makedirs(bin_dir)
    npm = os.path.join(bin_dir, "npm")
    with open(npm, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n")
        f.write('echo "npm noise on stdout"\n')
        if fail:
            f.write('echo "tsc: error TS1" >&2\nexit 2\n')
        else:
            f.write('/bin/mkdir -p dist && /bin/cp "$SHELL_SRC" dist/index.html\n')
    os.chmod(npm, 0o755)
    env = {"PATH": bin_dir, "SHELL_SRC": os.path.join(test.tmp, "shell-src.html")}
    patcher = mock.patch.dict(os.environ, env)
    patcher.start()
    test.addCleanup(patcher.stop)
    return web


class _PageTest(support.IsolatedTestCase):

    def setUp(self):
        super().setUp()
        self.data = self.data_dir()
        self.page = os.path.join(self.data, "index.html")

    def drop_cache(self):
        os.remove(self.cached_shell)

    def build(self, **hooks):
        return self.run_cli("build", "--data-dir", self.data, page_hooks=hooks)


class CachedShellTest(_PageTest):
    """Source 1: a cached shell, with no node or npm on PATH."""

    def test_import_writes_the_page_without_node(self):
        _no_npm_path(self)
        empty = os.path.join(self.tmp, "fresh")
        os.mkdir(empty, 0o700)
        with mock.patch.object(page, "WEB_DIR", os.path.join(support.REPO, "web")):
            with mock.patch.object(subprocess, "run", side_effect=AssertionError):
                code, _, err = self.run_cli(
                    "import", FIXTURE_AMAZON, "--data-dir", empty
                )
        self.assertEqual(code, 0, err)
        self.assertIn("page shell from cache", err)
        with open(os.path.join(empty, "index.html"), encoding="utf-8") as f:
            data = page_data_of(f.read())
        self.assertEqual(data["format"], page.FORMAT)
        self.assertEqual([s["id"] for s in data["stores"]], ["amazon"])
        self.assertEqual(
            sorted(o["id"] for o in data["orders"]),
            [
                "111-0000001-0000001",
                "111-0000002-0000002",
                "111-0000004-0000004",
                "202-0000003-0000003",
                "D01-0000005-0000005",
                "D01-0000006-0000006",
            ],
        )

    def test_build_command(self):
        _no_npm_path(self)
        code, out, err = self.build()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), self.page)
        code, out, _ = self.run_cli("build", "--json", "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out), {"path": self.page, "shell": "cache", "orders": 8}
        )

    def test_page_is_private_and_status_sees_it(self):
        self.build()
        self.assertEqual(stat.S_IMODE(os.stat(self.page).st_mode), 0o600)
        code, out, _ = self.run_cli("status", "--json", "--data-dir", self.data)
        self.assertEqual(code, 0)
        self.assertIsNotNone(json.loads(out)["page_built"])

    def test_a_damaged_cache_entry_is_replaced_by_a_download(self):
        with open(self.cached_shell, "w", encoding="utf-8") as f:
            f.write("<html>not a shell</html>")
        code, _, err = self.build(fetch=lambda url: support.TINY_SHELL)
        self.assertEqual(code, 0, err)
        with open(self.cached_shell, encoding="utf-8") as f:
            self.assertEqual(f.read(), support.TINY_SHELL)


class DownloadTest(_PageTest):
    """Source 3: the release download, fetched once and then cached."""

    def setUp(self):
        super().setUp()
        self.drop_cache()
        _no_npm_path(self)
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return support.TINY_SHELL

    def test_fetched_once_cached_and_reused(self):
        code, _, err = self.build(fetch=self.fetch)
        self.assertEqual(code, 0, err)
        self.assertIn("page shell from download", err)
        self.assertEqual(
            self.urls,
            [
                "https://github.com/curtisgalloway/order-history/releases/download/"
                f"v{__version__}/page-shell.html"
            ],
        )
        with open(self.cached_shell, encoding="utf-8") as f:
            self.assertEqual(f.read(), support.TINY_SHELL)
        code, _, err = self.build(fetch=self.fetch)
        self.assertEqual(code, 0, err)
        self.assertIn("page shell from cache", err)
        self.assertEqual(len(self.urls), 1)

    def test_the_cache_is_keyed_by_version(self):
        self.build(fetch=self.fetch, version="9.8.7")
        self.assertTrue(
            os.path.exists(os.path.join(self.shell_cache, "page-shell-9.8.7.html"))
        )
        self.assertFalse(os.path.exists(self.cached_shell))
        self.assertTrue(self.urls[0].endswith("/v9.8.7/page-shell.html"))

    def test_xdg_cache_home(self):
        xdg = os.path.join(self.tmp, "xdg-cache")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": xdg}):
            self.build(fetch=self.fetch)
        name = page.SHELL_NAME.format(version=__version__)
        self.assertTrue(os.path.exists(os.path.join(xdg, "order-history", name)))

    def test_a_download_that_is_not_a_shell_is_refused_and_not_cached(self):
        code, _, err = self.build(fetch=lambda url: "<html>login page</html>")
        self.assertEqual(code, 4)
        self.assertIn("the download is not a page shell", err)
        self.assertFalse(os.path.exists(self.cached_shell))
        self.assertFalse(os.path.exists(self.page))

    def test_the_real_download_function_is_size_capped(self):
        class Resp:  # pylint: disable=missing-class-docstring,missing-function-docstring

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n):
                return b"x" * n

        with mock.patch.object(page.urllib.request, "urlopen", return_value=Resp()):
            with self.assertRaises(ValueError):
                real_download("https://example.invalid/x")

    def test_a_truncated_download_exits_4(self):
        """http.client errors that aren't OSError become exit 4 (review F3)."""
        err = page.http.client.IncompleteRead(b"partial", 100)
        with mock.patch.object(page.urllib.request, "urlopen", side_effect=err):
            code, _, out = self.build(fetch=real_download)
        self.assertEqual(code, 4)
        self.assertIn("IncompleteRead", out)


class LockTest(_PageTest):
    """build takes the import lock, so it can't race an import (review F2)."""

    @unittest.skipIf(store.fcntl is None, "no fcntl: imports are unlocked")
    def test_build_refuses_while_an_import_runs(self):
        with store.import_lock(self.data):
            code, _, err = self.build()
        self.assertEqual(code, 20)
        self.assertIn("another import is running", err)
        self.assertFalse(os.path.exists(self.page))
        code, _, err = self.build()
        self.assertEqual(code, 0, err)


class LocalBuildTest(_PageTest):
    """Source 2: a checkout's web/ with npm on PATH; never cached."""

    def setUp(self):
        super().setUp()
        self.drop_cache()

    def test_local_build_is_used_and_not_cached(self):
        web = _fake_web(self, support.TINY_SHELL)
        code, out, err = self.run_cli(
            "build", "--json", "--data-dir", self.data, page_hooks={"web_dir": web}
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(
            json.loads(out)["shell"], "local build"
        )  # npm's noise kept out
        self.assertFalse(os.path.exists(self.cached_shell))

    def test_a_failed_local_build_falls_back_to_the_download(self):
        web = _fake_web(self, support.TINY_SHELL, fail=True)
        code, _, err = self.build(web_dir=web, fetch=lambda url: support.TINY_SHELL)
        self.assertEqual(code, 0, err)
        self.assertIn("page shell from download", err)

    def test_npm_gets_a_timeout(self):
        web = _fake_web(self, support.TINY_SHELL)
        calls = []

        def run(cmd, **kw):
            calls.append(kw.get("timeout"))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

        with mock.patch.object(page.subprocess, "run", run):
            code, _, err = self.build(web_dir=web)
        self.assertEqual(code, 4)
        self.assertEqual(calls, [page.NPM_TIMEOUT])
        self.assertIn("timed out", err)

    def test_all_sources_fail_names_each_reason(self):
        web = _fake_web(self, support.TINY_SHELL, fail=True)
        code, _, err = self.build(web_dir=web)
        self.assertEqual(code, 4)
        self.assertIn("`run build` exited 2: tsc: error TS1", err)
        self.assertIn("download failed (test: no network", err)
        self.assertIn(page.release_url(), err)


class OfflineTest(_PageTest):
    """No cache, no Node, no network: exit 4, and nothing changes."""

    def setUp(self):
        super().setUp()
        self.drop_cache()
        _no_npm_path(self)
        with open(self.page, "w", encoding="utf-8") as f:
            f.write("the old page")

    def assertPageUnchanged(self):  # pylint: disable=invalid-name
        with open(self.page, encoding="utf-8") as f:
            self.assertEqual(f.read(), "the old page")
        self.assertEqual(
            sorted(n for n in os.listdir(self.data) if n.startswith(".index")), []
        )

    def test_build_exits_4(self):
        code, out, err = self.build()
        self.assertEqual(code, 4)
        self.assertEqual(out, "")
        self.assertIn(page.release_url(), err)
        self.assertIn("The existing page is unchanged", err)
        self.assertPageUnchanged()

    def test_import_exits_4_and_rolls_back(self):
        downloads = os.path.join(self.tmp, "dl")
        test_import.write_amazon(
            os.path.join(downloads, "new"),
            test_import.NEW_PHYSICAL,
            test_import.NEW_DIGITAL,
        )
        before = support_snapshot(os.path.join(self.data, "amazon"))
        code, _, err = self.run_cli(
            "import",
            os.path.join(downloads, "new"),
            "--force",  # the fixture's current export is newer
            "--data-dir",
            self.data,
        )
        self.assertEqual(code, 4, err)
        self.assertIn("the previous export is current again", err)
        self.assertEqual(support_snapshot(os.path.join(self.data, "amazon")), before)
        self.assertPageUnchanged()

    def test_dry_run_needs_no_shell(self):
        code, _, err = self.run_cli(
            "import", FIXTURE_AMAZON, "--dry-run", "--data-dir", self.data
        )
        self.assertEqual(code, 0, err)
        self.assertPageUnchanged()


def support_snapshot(root):
    """{relative path: bytes} of every file under root."""
    snap = {}
    for folder, _, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as f:
                snap[os.path.relpath(path, root)] = f.read()
    return snap


class AtomicWriteTest(_PageTest):
    """The page is written to a temporary file and renamed into place."""

    def test_failed_rename_leaves_the_old_page_and_no_temp_file(self):
        with open(self.page, "w", encoding="utf-8") as f:
            f.write("the old page")
        with mock.patch.object(page.os, "replace", side_effect=OSError("disk full")):
            code, _, err = self.build()
        self.assertEqual(code, 4)
        self.assertIn("disk full", err)
        with open(self.page, encoding="utf-8") as f:
            self.assertEqual(f.read(), "the old page")
        self.assertEqual(
            sorted(os.listdir(self.data)),
            [".import.lock", "adafruit", "amazon", "index.html"],
        )


class InjectionTest(unittest.TestCase):
    """Order data holding </script> and friends can't break out of the element."""

    def shells(self):
        shells = [("tiny", support.TINY_SHELL)]
        if REAL_SHELL:
            with open(REAL_SHELL, encoding="utf-8") as f:
                shells.append(("built", f.read()))
        return shells

    def data(self):
        order = {
            "store": "amazon",
            "id": "111-0000099-0000099",
            "date": "2025-01-01",
            "currency": "USD",
            "items": [{"name": NASTY, "qty": "1"}, {"name": "a b\\u003c", "qty": "1"}],
        }
        return {"format": 1, "generated": "x", "stores": [], "orders": [order]}

    def test_data_survives_and_adds_no_elements(self):
        for label, shell in self.shells():
            with self.subTest(shell=label):
                before = scripts_of(shell)
                built = page.fill(shell, self.data())
                self.assertEqual(page_data_of(built), self.data())
                after = scripts_of(built)
                self.assertEqual(len(after), len(before))
                self.assertNotIn("<script>alert", built)
                text = [s for a, s in after if a.get("id") == "order-data"][0]
                self.assertNotIn("<", text)

    def test_script_text_has_no_angle_bracket(self):
        text = page.to_script_text({"x": NASTY})
        self.assertNotIn("<", text)
        self.assertEqual(json.loads(text), {"x": NASTY})

    def test_fill_refuses_a_page_without_the_element(self):
        with self.assertRaises(page.PageError):
            page.fill("<html></html>", self.data())
        with self.assertRaises(page.PageError):
            page.fill(support.TINY_SHELL + support.TINY_SHELL, self.data())


class HostileImportTest(_PageTest):
    """End to end: a product name holding </script> imports and stays data."""

    def test_hostile_title(self):
        downloads = os.path.join(self.tmp, "dl", "export")
        physical = [("111-0000098-0000098", "2025-09-01", "B0TESTX001", NASTY, "1.00")]
        test_import.write_amazon(downloads, physical, [])
        empty = os.path.join(self.tmp, "fresh")
        os.mkdir(empty, 0o700)
        code, _, err = self.run_cli("import", downloads, "--data-dir", empty)
        self.assertEqual(code, 0, err)
        with open(os.path.join(empty, "index.html"), encoding="utf-8") as f:
            data = page_data_of(f.read())
        self.assertEqual(data["orders"][0]["items"][0]["name"], NASTY)


class PageDataTest(unittest.TestCase):
    """The data's shape, and the format number shared with the page."""

    def test_format_matches_the_page(self):
        with open(
            os.path.join(support.REPO, "web", "src", "load.ts"), encoding="utf-8"
        ) as f:
            found = re.search(r"export const DATA_FORMAT = (\d+);", f.read())
        self.assertIsNotNone(found)
        self.assertEqual(int(found.group(1)), page.FORMAT)

    def test_shape(self):
        loaded = []
        for v in vendors.VENDORS:
            loaded.append((v, v.load(os.path.join(support.FIXTURE_DATA, v.ID))))
        loaded.append((vendors.VENDORS[0], None))  # a vendor with no export: skipped
        data = page.page_data(loaded, today=datetime.date(2025, 1, 2))
        self.assertEqual(data["format"], page.FORMAT)
        self.assertEqual(data["generated"], "2025-01-02")
        self.assertEqual(
            data["stores"],
            [
                {
                    "id": "amazon",
                    "name": "Amazon",
                    "source": "Order History.csv + Digital Content Orders.csv",
                },
                {
                    "id": "adafruit",
                    "name": "Adafruit",
                    "source": "order_history.csv + items.json",
                },
            ],
        )
        dates = [o["date"] for o in data["orders"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertNotIn("status", data["orders"][-1], "empty fields are dropped")


if __name__ == "__main__":
    unittest.main()
