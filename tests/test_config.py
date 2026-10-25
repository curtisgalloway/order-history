# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Data-folder resolution, init and the missing-folder exit (design R2)."""

import json
import os
import stat
import unittest
from unittest import mock

import support
from order_history import config


class ResolveTest(support.IsolatedTestCase):
    """The precedence: flag, then env, then config file, then default."""

    def setUp(self):
        super().setUp()
        self.flag = os.path.join(self.tmp, "flag")
        self.env = os.path.join(self.tmp, "env")
        self.cfg = os.path.join(self.tmp, "cfg")

    def write_config(self, data_dir):
        path = config.config_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"data_dir": data_dir}, f)

    def test_default(self):
        self.assertEqual(
            config.resolve(),
            (os.path.join(self.home, "Documents", "Order History"), "default"),
        )

    def test_config_beats_default(self):
        self.write_config(self.cfg)
        self.assertEqual(config.resolve(), (self.cfg, "config"))

    def test_env_beats_config(self):
        self.write_config(self.cfg)
        os.environ["ORDER_HISTORY_DIR"] = self.env
        self.assertEqual(config.resolve(), (self.env, "env"))

    def test_flag_beats_env(self):
        self.write_config(self.cfg)
        os.environ["ORDER_HISTORY_DIR"] = self.env
        self.assertEqual(config.resolve(self.flag), (self.flag, "flag"))

    def test_config_path_honors_xdg(self):
        self.assertEqual(
            config.config_path(),
            os.path.join(self.home, ".config", "order-history", "config.json"),
        )
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp, "xdg")
        self.assertEqual(
            config.config_path(),
            os.path.join(self.tmp, "xdg", "order-history", "config.json"),
        )

    def test_tilde_and_relative_paths_are_made_absolute(self):
        self.assertEqual(config.resolve("~/x"), (os.path.join(self.home, "x"), "flag"))
        self.assertTrue(os.path.isabs(config.resolve("rel")[0]))

    def test_default_is_under_home_not_the_checkout(self):
        self.assertTrue(config.DEFAULT_DIR.startswith("~" + os.sep))
        with mock.patch.dict(os.environ, {"HOME": support.REAL_HOME}):
            path = os.path.abspath(os.path.expanduser(config.DEFAULT_DIR))
        self.assertFalse(path.startswith(support.REPO + os.sep))

    def test_broken_config_is_an_error(self):
        path = config.config_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(config.ConfigError):
            config.resolve()


class InitTest(support.IsolatedTestCase):
    """`init` creates the folder 0700 and records it for later commands."""

    def test_init_creates_0700_and_records(self):
        target = os.path.join(self.tmp, "T")
        old = os.umask(0o022)
        try:
            code, out, err = self.run_cli("init", "--data-dir", target)
        finally:
            os.umask(old)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), target)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o700)
        with open(config.config_path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"data_dir": target})
        code, out, err = self.run_cli("status", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["data_dir"], target)

    def test_init_keeps_an_existing_folder_and_other_config_keys(self):
        target = os.path.join(self.tmp, "T")
        os.mkdir(target, 0o755)
        os.chmod(target, 0o755)
        path = config.config_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"other": 1}, f)
        code, out, _ = self.run_cli("--json", "init", "--data-dir", target)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["created"], False)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o755)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"other": 1, "data_dir": target})

    def test_init_does_not_overwrite_a_broken_config(self):
        path = config.config_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        target = os.path.join(self.tmp, "T")
        code, _, err = self.run_cli("init", "--data-dir", target)
        self.assertEqual(code, 2)
        self.assertIn("can't read", err)
        self.assertFalse(os.path.exists(target), "nothing is created")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{not json")

    def test_init_on_a_file_exits_2(self):
        target = os.path.join(self.tmp, "file")
        with open(target, "w", encoding="utf-8") as f:
            f.write("x")
        code, _, err = self.run_cli("init", "--data-dir", target)
        self.assertEqual(code, 2)
        self.assertIn("is not a folder", err)

    def test_commands_before_init_exit_3_naming_init(self):
        for argv in (["status"], ["search", "x"], ["order", "1"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 3)
                self.assertEqual(out, "")
                self.assertIn("order-history init", err)


if __name__ == "__main__":
    unittest.main()
