# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Shared test setup: the package on sys.path, fixtures, an isolated home."""

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


class IsolatedTestCase(unittest.TestCase):
    """Runs each test with HOME, XDG_CONFIG_HOME and ORDER_HISTORY_DIR isolated."""

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
        os.environ.pop("ORDER_HISTORY_DIR", None)

    def data_dir(self, vendors=("amazon", "adafruit")):
        """A copy of the fixture data folder holding only `vendors`."""
        path = os.path.join(self.tmp, "data")
        os.mkdir(path, 0o700)
        for vendor in vendors:
            shutil.copytree(
                os.path.join(FIXTURE_DATA, vendor), os.path.join(path, vendor)
            )
        return path

    def run_cli(self, *argv, registry=None):
        """(exit code, stdout, stderr) of cli.main(argv)."""
        from order_history import cli  # pylint: disable=import-outside-toplevel

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv), registry=registry)
            except SystemExit as e:  # argparse usage errors and --version
                code = e.code
        return code, out.getvalue(), err.getvalue()
