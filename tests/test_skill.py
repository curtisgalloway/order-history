# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The skill documents, --skill, the plugin manifests and packaging (design R8)."""

import json
import os
import re
import subprocess
import sys
import unittest

import support
from order_history import __version__, cli, vendors

SKILL_DIR = os.path.join(support.REPO, "skills", "order-history")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
PLUGIN_JSON = os.path.join(support.REPO, ".claude-plugin", "plugin.json")
MARKETPLACE_JSON = os.path.join(support.REPO, ".claude-plugin", "marketplace.json")
STAMP = f"\nPrinted by `order-history --skill`, version {__version__}.\n"


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def split_frontmatter(text):
    """(frontmatter through its closing ---, the rest)."""
    end = text.index("\n---\n", 3) + len("\n---\n")
    return text[:end], text[end:]


class SkillOutputTest(support.IsolatedTestCase):
    """--skill prints SKILL.md exactly, plus one version line."""

    def test_skill_flag_is_skill_md_with_the_version_line(self):
        code, out, err = self.run_cli("--skill")
        self.assertEqual(code, 0, err)
        front, rest = split_frontmatter(read(SKILL_MD))
        self.assertEqual(out, front + STAMP + rest)
        self.assertEqual(err, "")

    def test_skill_command_prints_the_same(self):
        _, flag_out, _ = self.run_cli("--skill")
        code, out, err = self.run_cli("skill")
        self.assertEqual(code, 0, err)
        self.assertEqual(out, flag_out)

    def test_needs_no_data_folder(self):
        # --skill is how an agent learns the tool, so it works before init.
        code, _, _ = self.run_cli("--skill")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.home, "Documents")))

    def test_emitted_text_is_a_complete_skill(self):
        _, out, _ = self.run_cli("--skill")
        front, _ = split_frontmatter(out)
        self.assertTrue(out.startswith("---\nname: order-history\ndescription: "))
        self.assertIn("\ndescription: ", front)

    def test_entry_script_writes_utf8_bytes_under_a_c_locale(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LC_")}
        env.update(LANG="C", LC_ALL="C", PYTHONIOENCODING="ascii")
        out = subprocess.run(
            [sys.executable, support.ENTRY, "--skill"],
            capture_output=True,
            env=env,
            check=True,
        ).stdout
        front, rest = split_frontmatter(read(SKILL_MD))
        self.assertEqual(out, (front + STAMP + rest).encode("utf-8"))

    def test_vendor_docs(self):
        for vendor in vendors.VENDORS:
            with self.subTest(vendor=vendor.ID):
                code, out, err = self.run_cli("skill", vendor.ID)
                self.assertEqual(code, 0, err)
                path = os.path.join(SKILL_DIR, "vendors", vendor.ID + ".md")
                self.assertEqual(out, read(path))

    def test_json_wraps_the_text(self):
        _, flag_out, _ = self.run_cli("--skill")
        code, out, err = self.run_cli("skill", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            json.loads(out), {"store": None, "version": __version__, "text": flag_out}
        )
        code, out, _ = self.run_cli("skill", "amazon", "--json")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["store"], "amazon")
        self.assertEqual(
            doc["text"], read(os.path.join(SKILL_DIR, "vendors", "amazon.md"))
        )

    def test_unknown_store_exits_2(self):
        code, out, err = self.run_cli("skill", "nosuchstore")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("known: amazon, adafruit", err)

    def test_registered_store_without_a_doc_exits_3(self):
        fake = type("Vendor", (), {"ID": "nodoc", "NAME": "No doc"})
        code, _, err = self.run_cli("skill", "nodoc", registry=[fake])
        self.assertEqual(code, 3)
        self.assertIn("no instructions", err)


class SkillDocumentsTest(unittest.TestCase):
    """What the shipped documents promise, checked against the code."""

    def test_packaged_copies_are_the_skill_files(self):
        # The package holds symbolic links, so the files can't drift apart.
        package = os.path.join(support.SCRIPTS, "order_history")
        pairs = [(os.path.join(package, cli.SKILL_RESOURCE), SKILL_MD)] + [
            (
                os.path.join(package, "vendors", v.ID + ".md"),
                os.path.join(SKILL_DIR, "vendors", v.ID + ".md"),
            )
            for v in vendors.VENDORS
        ]
        for packaged, shipped in pairs:
            with self.subTest(packaged=packaged):
                self.assertEqual(os.path.realpath(packaged), os.path.realpath(shipped))

    def test_one_vendor_doc_per_registered_vendor(self):
        skill = read(SKILL_MD)
        docs = sorted(os.listdir(os.path.join(SKILL_DIR, "vendors")))
        self.assertEqual(docs, sorted(v.ID + ".md" for v in vendors.VENDORS))
        self.assertIn("vendors/<store>.md", skill)

    def test_privacy_note_in_skill_and_readme(self):
        for path in (SKILL_MD, os.path.join(support.REPO, "README.md")):
            with self.subTest(path=path):
                self.assertIn("model provider", " ".join(read(path).split()))

    def test_no_removed_search_commands_in_the_docs(self):
        paths = [
            SKILL_MD,
            os.path.join(SKILL_DIR, "vendors", "amazon.md"),
            os.path.join(SKILL_DIR, "vendors", "adafruit.md"),
            os.path.join(support.REPO, "README.md"),
            os.path.join(support.REPO, "AGENTS.md"),
            os.path.join(support.REPO, "GLOSSARY.md"),
        ]
        # The migration steps may name the old build's data file, which an old
        # checkout still holds; nothing else under search/app is a live path.
        removed = re.compile(
            r"search/(build|fetch_\w+)\.py"
            r"|search/app(?!/src/generated/data\.json)"
            r"|npm --prefix search"
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertIsNone(removed.search(read(path)))

    def test_every_documented_command_exists(self):
        parser = cli.build_parser()
        commands = set(parser._subparsers._group_actions[0].choices)  # pylint: disable=protected-access
        # In code spans and at the start of lines in code blocks.
        used = set(re.findall(r"(?m)(?:^|`)order-history (\w+)", read(SKILL_MD)))
        self.assertLessEqual(used, commands)
        self.assertLessEqual(
            {"init", "import", "search", "order", "status", "update", "build"}, used
        )


class PackagingTest(unittest.TestCase):
    """The plugin manifests and pyproject.toml agree with the package."""

    def test_plugin_manifest(self):
        manifest = json.loads(read(PLUGIN_JSON))
        self.assertEqual(manifest["name"], "order-history")
        # The plugin's version is the tool's, so both move at a release.
        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertTrue(os.path.isfile(SKILL_MD))  # found by the default skills/ scan

    def test_marketplace_lists_this_repo_as_the_plugin(self):
        market = json.loads(read(MARKETPLACE_JSON))
        self.assertEqual(
            [(p["name"], p["source"]) for p in market["plugins"]],
            [("order-history", "./")],
        )
        self.assertNotIn("version", market["plugins"][0])  # plugin.json's wins

    def test_pyproject(self):
        try:
            import tomllib  # pylint: disable=import-outside-toplevel
        except ImportError:  # Python 3.10
            self.skipTest("tomllib needs Python 3.11")
        with open(os.path.join(support.REPO, "pyproject.toml"), "rb") as f:
            project = tomllib.load(f)
        self.assertEqual(
            project["project"]["scripts"], {"order-history": "order_history.cli:main"}
        )
        self.assertTrue(project["tool"]["uv"]["package"])
        setuptools = project["tool"]["setuptools"]
        self.assertEqual(
            setuptools["package-dir"], {"": "skills/order-history/scripts"}
        )
        self.assertEqual(
            setuptools["dynamic"]["version"], {"attr": "order_history.__version__"}
        )
        self.assertEqual(
            setuptools["package-data"],
            {"order_history": [cli.SKILL_RESOURCE], "order_history.vendors": ["*.md"]},
        )


if __name__ == "__main__":
    unittest.main()
