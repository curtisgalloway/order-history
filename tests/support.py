# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Shared test setup: the package on sys.path, fixtures, an isolated home.

Every IsolatedTestCase also gets a tiny page shell in its isolated cache, and
page.py's local build and download and fetching.py's network call are switched
off, so no test runs npm or touches the network unless it passes its own hooks.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
SCRIPTS = os.path.join(REPO, "skills", "order-history", "scripts")
ENTRY = os.path.join(SCRIPTS, "order-history")
FIXTURES = os.path.join(TESTS, "fixtures")
FIXTURE_DATA = os.path.join(FIXTURES, "data")
# The real home folder, read before any test isolates HOME.
REAL_HOME = os.path.expanduser("~")

if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

# pylint: disable=wrong-import-position
from order_history import __version__, fetching, page

# A minimal page shell: the empty order-data element and nothing else.
TINY_SHELL = (
    "<!DOCTYPE html><html><body><div id=root></div>"
    + page.PLACEHOLDER
    + "</body></html>"
)


def no_fetch(url):
    """A download stub that fails as offline does."""
    raise OSError(f"test: no network ({url})")


def no_urlopen(req, timeout):
    """The default network call in tests: fails the test outright."""
    raise AssertionError(f"test: unstubbed request to {req.full_url} ({timeout})")


class IsolatedTestCase(unittest.TestCase):
    """Runs each test with HOME, XDG_* and ORDER_HISTORY_DIR isolated."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.home = os.path.join(self.tmp, "home")
        os.mkdir(self.home)
        env = {"HOME": self.home}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("XDG_CONFIG_HOME", None)
        os.environ.pop("XDG_CACHE_HOME", None)
        os.environ.pop("ORDER_HISTORY_DIR", None)
        # No real npm build and no network by default.
        for name, value in (
            ("WEB_DIR", os.path.join(self.tmp, "no-web")),
            ("download", no_fetch),
        ):
            patcher = mock.patch.object(page, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(fetching, "http_read", no_urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("ADAFRUIT_EMAIL", None)
        self.shell_cache = page.cache_dir()
        os.makedirs(self.shell_cache)
        self.cached_shell = os.path.join(
            self.shell_cache, page.SHELL_NAME.format(version=__version__)
        )
        with open(self.cached_shell, "w", encoding="utf-8") as f:
            f.write(TINY_SHELL)

    def data_dir(self, vendors=("amazon", "adafruit")):
        """A copy of the fixture data folder holding only `vendors`."""
        path = os.path.join(self.tmp, "data")
        os.mkdir(path, 0o700)
        for vendor in vendors:
            shutil.copytree(
                os.path.join(FIXTURE_DATA, vendor), os.path.join(path, vendor)
            )
        return path

    def run_cli(self, *argv, registry=None, page_hooks=None, fetch_hooks=None):
        """(exit code, stdout, stderr) of cli.main(argv)."""
        from order_history import cli  # pylint: disable=import-outside-toplevel

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(
                    list(argv),
                    registry=registry,
                    page_hooks=page_hooks,
                    fetch_hooks=fetch_hooks,
                )
            except SystemExit as e:  # argparse usage errors and --version
                code = e.code
        return code, out.getvalue(), err.getvalue()
