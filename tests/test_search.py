# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""search.py against the shared case file and the page's matching rules."""

import json
import os
import unittest

import support
from order_history import model, search, vendors

CASES = os.path.join(support.TESTS, "search_cases.json")


def _fixture_orders():
    orders = []
    for v in vendors.VENDORS:
        orders += v.load(os.path.join(support.FIXTURE_DATA, v.ID))
    return model.finish(orders)


class CaseFileTest(unittest.TestCase):
    """Every case in search_cases.json returns exactly its expected IDs."""

    def test_cases(self):
        with open(CASES, encoding="utf-8") as f:
            cases = json.load(f)["cases"]
        orders = _fixture_orders()
        names = {v.ID: v.NAME for v in vendors.VENDORS}
        for case in cases:
            with self.subTest(case=case):
                got = search.search(
                    orders,
                    search.parse_terms(case["query"]),
                    names,
                    store=case.get("store"),
                    kind=case.get("kind"),
                )
                self.assertEqual([o["id"] for o in got], case["expect"])


class RulesTest(unittest.TestCase):
    """The haystacks and the per-item rule, as search.ts defines them."""

    def test_only_matching_items_are_returned(self):
        got = search.search(_fixture_orders(), ["wire"], {"amazon": "Amazon"})
        self.assertEqual([i["name"] for i in got[0]["items"]], ["Solder Wire Spool"])

    def test_order_fields_count_toward_each_item(self):
        got = search.search(_fixture_orders(), ["tools", "springfield"], {})
        self.assertEqual(got, [], "the shipping address is not searched")
        got = search.search(
            _fixture_orders(), ["amazon", "spool"], {"amazon": "Amazon"}
        )
        self.assertEqual(len(got), 1)

    def test_haystacks(self):
        order = model.new_order(
            "s", "ID-1", "2024-01-01", status="X", site="Site", shipMethod="Ship"
        )
        self.assertEqual(
            search.order_hay(order, "Store"),
            "store id-1 2024-01-01 x site ship physical",
        )
        item = model.new_item("Name", asin="ASIN", department="Dept")
        self.assertEqual(search.item_hay(item), "name asin  dept")

    def test_parse_terms(self):
        self.assertEqual(search.parse_terms("  A\tb  C "), ["a", "b", "c"])

    def test_input_is_not_modified(self):
        orders = _fixture_orders()
        before = json.dumps(orders)
        search.search(orders, ["wire"], {})
        self.assertEqual(json.dumps(orders), before)


if __name__ == "__main__":
    unittest.main()
