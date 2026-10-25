# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""`update`: Adafruit item lookups and opt-in Amazon images, network stubbed.

Every request goes to a FakeNet; the clock and the jitter are stubbed too, so
these tests never reach a store and never sleep.
"""

import contextlib
import datetime
import email.message
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request

import support
from order_history import fetching, store
from order_history.vendors import adafruit, amazon

ROBOTS_OK = b"User-agent: *\nDisallow: /checkout\n"
ROBOTS_NO = b"User-agent: *\nDisallow: /index.php\n"
TODAY = datetime.date(2026, 1, 2)
TEST_EMAIL = "buyer@example.com"
# Orders written by _adafruit_csv(); none is in items.json.
NEW_ORDERS = ["1000011-2000000011", "1000012-2000000012", "1000013-2000000013"]


def http_error(url, code):
    """An HTTPError as urllib raises it for status `code`, closed as http_read does."""
    error = urllib.error.HTTPError(
        url, code, f"status {code}", email.message.Message(), None
    )
    error.close()
    return error


def order_page(order_id, items=(("Example Widget", "9001", "4.95", "2", "9.90"),)):
    """An invented order-status page in the layout parse_items() reads."""
    rows = "".join(
        '<div class="row confirm-cart mobile-text-wrapper">'
        f'<div class="col-lg-5 col-md-5"><a href="/product/{pid}">{name}'
        f'<span class="product_id">PID: {pid}</span></a>'
        f'<img alt="" src="https://cdn.example.com/{pid}.jpg"></div>'
        f'<div class="col-lg-2 price">${unit}</div>'
        f'<div class="col-lg-2 qty">{qty}</div>'
        f'<div class="col-lg-2 total">${total}</div>'
        "</div>"
        for name, pid, unit, qty, total in items
    )
    return f"<html><h2>Order #{order_id}</h2>{rows}</html>".encode()


class FakeNet:
    """urlopen(request, timeout) for tests: answers by URL, records each call.

    `routes` maps a URL, or a callable taking the request, to bytes or an
    exception (raised), or a list of those consumed in order.
    """

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []
        self._lock = threading.Lock()  # Amazon's phase A calls from threads

    def __call__(self, req, timeout):
        with self._lock:
            self.calls.append(req)
        answer = self.routes.get(req.full_url)
        if answer is None:
            for key, value in self.routes.items():
                if callable(key) and key(req):
                    answer = value
                    break
        if answer is None:
            raise AssertionError(f"unexpected request to {req.full_url}")
        if isinstance(answer, list):
            with self._lock:
                answer = answer.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def urls(self):
        """Every URL requested, in order."""
        return [r.full_url for r in self.calls]

    def lookups(self):
        """The order numbers posted to Adafruit's lookup form, in order."""
        return [
            urllib.parse.parse_qs(r.data.decode())["order_number"][0]
            for r in self.calls
            if r.full_url == adafruit.LOOKUP_URL
        ]


def adafruit_routes(*pages):
    """Robots allowing the lookup, then `pages` (bytes or errors) in order."""
    return {adafruit.ROBOTS_URL: ROBOTS_OK, adafruit.LOOKUP_URL: list(pages)}


class UpdateCase(support.IsolatedTestCase):
    """A data folder plus stubbed network, clock and jitter."""

    def setUp(self):
        super().setUp()
        self.sleeps = []
        self.uniform_args = []

    def hooks(self, net):
        """fetch_hooks for run_cli: net, and a clock that records sleeps."""

        def uniform(a, b):
            self.uniform_args.append((a, b))
            return b  # the most jitter the rules allow

        return {
            "urlopen": net,
            "sleep": self.sleeps.append,
            "uniform": uniform,
            "random": lambda: 0.0,
            "today": TODAY,
        }

    def update(self, net, *argv):
        """run_cli("update", ...) on self.data with net stubbed."""
        return self.run_cli(
            "update", "--data-dir", self.data, *argv, fetch_hooks=self.hooks(net)
        )

    def items_json(self):
        path = os.path.join(self.data, "adafruit", adafruit.ITEMS_JSON)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def write_email(self, value=TEST_EMAIL):
        path = os.path.join(self.data, "adafruit", adafruit.EMAIL_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(value + "\n")

    def adafruit_only(self, order_ids=None):
        """A data folder with only Adafruit, holding `order_ids`, none fetched."""
        self.data = self.data_dir(vendors=("adafruit",))
        os.unlink(os.path.join(self.data, "adafruit", adafruit.ITEMS_JSON))
        rows = [
            "order_id,date_purchased,order_status,subtotal,shipping,tax,coupon,"
            "gift_certificate,total,refund,shipping_method"
        ]
        for n, oid in enumerate(order_ids or NEW_ORDERS):
            rows.append(
                oid.replace("-", " ") + f",2025 0{n + 1} 01 10:00:00,Shipped,"
                "9.90,0.00,0.00,,,9.90,0.00,Ground"
            )
        path = os.path.join(self.data, "adafruit", "current", adafruit.ORDERS_CSV)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        self.write_email()

    def page_text(self):
        with open(os.path.join(self.data, "index.html"), encoding="utf-8") as f:
            return f.read()


class AdafruitUpdateTest(UpdateCase):
    """Item lines for unfetched orders, with the old fetcher's politeness rules."""

    def test_fills_unfetched_orders_only_and_rebuilds(self):
        self.data = self.data_dir(vendors=("adafruit",))
        self.write_email()
        before = self.items_json()
        net = FakeNet(adafruit_routes(order_page("1000002-2000000002")))
        code, out, err = self.update(net)
        self.assertEqual(code, 0, err)
        # robots.txt first, then one lookup: the fetched order isn't asked again.
        self.assertEqual(net.urls(), [adafruit.ROBOTS_URL, adafruit.LOOKUP_URL])
        self.assertEqual(net.lookups(), ["1000002-2000000002"])
        post = urllib.parse.parse_qs(net.calls[1].data.decode())
        self.assertEqual(
            post, {"email": [TEST_EMAIL], "order_number": ["1000002-2000000002"]}
        )
        for req in net.calls:
            self.assertEqual(req.get_header("User-agent"), adafruit.UA)
        items = self.items_json()
        self.assertEqual(items["1000001-2000000001"], before["1000001-2000000001"])
        self.assertEqual(
            items["1000002-2000000002"],
            {
                "fetched": "2026-01-02",
                "items": [
                    {
                        "name": "Example Widget",
                        "qty": "2",
                        "unit": "4.95",
                        "total": "9.90",
                        "pid": "9001",
                        "url": "https://www.adafruit.com/product/9001",
                        "imageUrl": "https://cdn.example.com/9001.jpg",
                    }
                ],
            },
        )
        self.assertIn("Example Widget", self.page_text())
        self.assertIn("adafruit: 1 saved, 0 failed, 0 still missing", out)
        self.assertIn("page: rebuilt", out)
        self.assertEqual(self.sleeps, [])  # one lookup: nothing to wait between
        for text in (out, err):
            self.assertNotIn(TEST_EMAIL, text)

    def test_waits_at_least_the_delay_between_requests(self):
        self.adafruit_only()
        net = FakeNet(adafruit_routes(*(order_page(o) for o in NEW_ORDERS)))
        code, _, err = self.update(net)
        self.assertEqual(code, 0, err)
        self.assertEqual(net.lookups(), NEW_ORDERS)
        # One wait between each pair of lookups, none before the first.
        self.assertEqual(len(self.sleeps), len(NEW_ORDERS) - 1)
        self.assertEqual(self.uniform_args, [(0, 5.0)] * 2)
        self.assertEqual(self.sleeps, [15.0, 15.0])
        for wait in self.sleeps:
            self.assertGreaterEqual(wait, adafruit.MIN_DELAY)

    def test_crawl_delay_lengthens_the_wait(self):
        self.adafruit_only()
        routes = adafruit_routes(*(order_page(o) for o in NEW_ORDERS))
        routes[adafruit.ROBOTS_URL] = b"User-agent: *\nCrawl-delay: 30\n"
        code, _, err = self.update(FakeNet(routes))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.uniform_args, [(0, 15.0)] * 2)
        self.assertEqual(self.sleeps, [45.0, 45.0])

    def test_minimum_delay_without_jitter(self):
        self.adafruit_only()
        net = FakeNet(adafruit_routes(*(order_page(o) for o in NEW_ORDERS)))
        hooks = self.hooks(net)
        hooks["uniform"] = lambda a, b: a
        code, _, _ = self.run_cli("update", "--data-dir", self.data, fetch_hooks=hooks)
        self.assertEqual(code, 0)
        self.assertEqual(self.sleeps, [10.0, 10.0])

    def test_robots_disallow_exits_20_without_fetching(self):
        self.adafruit_only()
        net = FakeNet({adafruit.ROBOTS_URL: ROBOTS_NO})
        code, out, err = self.update(net)
        self.assertEqual(code, 20)
        self.assertEqual(net.urls(), [adafruit.ROBOTS_URL])
        self.assertEqual(self.items_json(), {})
        self.assertFalse(os.path.exists(os.path.join(self.data, "index.html")))
        self.assertIn("robots.txt disallows", out + err)
        self.assertIn("page: unchanged", out)

    def test_robots_unreadable_exits_20_without_fetching(self):
        for answer in (
            http_error(adafruit.ROBOTS_URL, 403),
            urllib.error.URLError("no route"),
            TimeoutError("timed out"),
        ):
            with self.subTest(answer=answer):
                self.adafruit_only()
                net = FakeNet({adafruit.ROBOTS_URL: answer})
                code, out, _ = self.update(net, "--json")
                self.assertEqual(code, 20)
                self.assertEqual(net.urls(), [adafruit.ROBOTS_URL])
                doc = json.loads(out)
                self.assertEqual(
                    doc["vendors"][0]["stopped"]["reason"], "robots_unreadable"
                )
                os.rename(self.data, self.data + f"-{len(os.listdir(self.tmp))}")

    def test_throttled_midway_exits_21_and_keeps_what_was_fetched(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                self.adafruit_only()
                net = FakeNet(
                    adafruit_routes(
                        order_page(NEW_ORDERS[0]),
                        http_error(adafruit.LOOKUP_URL, status),
                    )
                )
                code, out, err = self.update(net, "--json")
                self.assertEqual(code, 21, err)
                # Stops at the throttle: the third order is never asked for.
                self.assertEqual(net.lookups(), NEW_ORDERS[:2])
                self.assertEqual(list(self.items_json()), [NEW_ORDERS[0]])
                doc = json.loads(out)
                result = doc["vendors"][0]
                self.assertEqual(result["stopped"]["reason"], "throttled")
                self.assertEqual(result["changed"], 1)
                self.assertEqual(result["pending"], 2)
                self.assertEqual(result["requests"], 3)
                # The page is rebuilt with what was fetched.
                self.assertEqual(doc["page"], os.path.join(self.data, "index.html"))
                self.assertIn("Example Widget", self.page_text())
                os.rename(self.data, self.data + f"-{status}")

    def test_throttled_at_once_exits_20(self):
        self.adafruit_only()
        net = FakeNet(adafruit_routes(http_error(adafruit.LOOKUP_URL, 429)))
        code, _, _ = self.update(net)
        self.assertEqual(code, 20)
        self.assertEqual(net.lookups(), NEW_ORDERS[:1])
        self.assertEqual(self.items_json(), {})
        self.assertFalse(os.path.exists(os.path.join(self.data, "index.html")))

    def test_other_failures_are_skipped_not_retried(self):
        self.adafruit_only()
        net = FakeNet(
            adafruit_routes(
                http_error(adafruit.LOOKUP_URL, 404),
                b"<html>Sign in</html>",  # not the order's page
                order_page(NEW_ORDERS[2]),
            )
        )
        code, out, _ = self.update(net, "--json")
        self.assertEqual(code, 21)
        self.assertEqual(net.lookups(), NEW_ORDERS)
        self.assertEqual(list(self.items_json()), [NEW_ORDERS[2]])
        failed = json.loads(out)["vendors"][0]["failed"]
        self.assertEqual(
            failed,
            [
                {"id": NEW_ORDERS[0], "error": "HTTP 404"},
                {
                    "id": NEW_ORDERS[1],
                    "error": "response is not this order's status page",
                },
            ],
        )

    def test_every_lookup_failing_exits_20(self):
        self.adafruit_only(NEW_ORDERS[:1])
        net = FakeNet(adafruit_routes(b"<html>Sign in</html>"))
        code, _, _ = self.update(net)
        self.assertEqual(code, 20)

    def test_nothing_missing_makes_no_requests(self):
        self.adafruit_only(NEW_ORDERS[:1])
        net = FakeNet(adafruit_routes(order_page(NEW_ORDERS[0])))
        self.assertEqual(self.update(net)[0], 0)
        page = os.path.join(self.data, "index.html")
        built = os.stat(page).st_mtime_ns
        # Second run: no email needed, no request, no rebuild.
        os.unlink(os.path.join(self.data, "adafruit", adafruit.EMAIL_FILE))
        net = FakeNet()
        code, out, err = self.update(net)
        self.assertEqual(code, 0, err)
        self.assertEqual(net.calls, [])
        self.assertEqual(os.stat(page).st_mtime_ns, built)
        self.assertIn("adafruit: 0 saved, 0 failed, 0 still missing, 0 requests", out)
        self.assertIn("page: unchanged", out)

    def test_missing_email_exits_3_without_requests(self):
        self.adafruit_only()
        os.unlink(os.path.join(self.data, "adafruit", adafruit.EMAIL_FILE))
        net = FakeNet()
        code, out, err = self.update(net, "--json")
        self.assertEqual(code, 3)
        self.assertEqual(net.calls, [])
        error = json.loads(out)["vendors"][0]["error"]
        self.assertEqual(error["code"], 3)
        self.assertIn("--email", error["message"])
        self.assertIn("ADAFRUIT_EMAIL", err)

    def test_email_sources_in_order(self):
        self.adafruit_only()
        vendor_dir = os.path.join(self.data, "adafruit")
        self.assertEqual(adafruit.lookup_email(vendor_dir), TEST_EMAIL)
        os.environ["ADAFRUIT_EMAIL"] = "env@example.com"
        self.assertEqual(adafruit.lookup_email(vendor_dir), "env@example.com")
        self.assertEqual(
            adafruit.lookup_email(vendor_dir, "flag@example.com"), "flag@example.com"
        )
        os.unlink(os.path.join(vendor_dir, adafruit.EMAIL_FILE))
        del os.environ["ADAFRUIT_EMAIL"]
        self.assertEqual(adafruit.lookup_email(vendor_dir), "")

    def test_email_flag_is_used(self):
        self.adafruit_only(NEW_ORDERS[:1])
        os.unlink(os.path.join(self.data, "adafruit", adafruit.EMAIL_FILE))
        net = FakeNet(adafruit_routes(order_page(NEW_ORDERS[0])))
        code, _, _ = self.update(net, "--email", "flag@example.com")
        self.assertEqual(code, 0)
        post = urllib.parse.parse_qs(net.calls[1].data.decode())
        self.assertEqual(post["email"], ["flag@example.com"])

    def test_dry_run_sends_nothing_and_writes_nothing(self):
        self.adafruit_only()
        net = FakeNet()
        code, out, _ = self.update(net, "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, [])
        doc = json.loads(out)
        self.assertTrue(doc["dry_run"])
        self.assertEqual(doc["vendors"][0]["pending"], 3)
        self.assertIsNone(doc["page"])
        self.assertEqual(self.items_json(), {})

    def test_another_update_running_exits_20(self):
        self.adafruit_only()
        net = FakeNet()
        with store.update_lock(self.data):
            code, _, err = self.update(net)
        self.assertEqual(code, 20)
        self.assertIn("another update is running", err)
        self.assertEqual(net.calls, [])

    def test_import_running_at_rebuild_exits_21(self):
        self.adafruit_only(NEW_ORDERS[:1])
        net = FakeNet(adafruit_routes(order_page(NEW_ORDERS[0])))
        with contextlib.ExitStack() as held:

            def urlopen(req, timeout):
                # An import starts while the lookups run, after the read.
                if req.full_url == adafruit.LOOKUP_URL:
                    held.enter_context(store.import_lock(self.data))
                return net(req, timeout)

            hooks = self.hooks(net)
            hooks["urlopen"] = urlopen
            code, _, err = self.run_cli(
                "update", "--data-dir", self.data, fetch_hooks=hooks
            )
        self.assertEqual(code, 21)
        self.assertIn("order-history build", err)
        self.assertEqual(list(self.items_json()), NEW_ORDERS[:1])

    def test_import_running_exits_20_before_any_request(self):
        # Review F3: the exports are read under the import lock.
        self.adafruit_only()
        net = FakeNet()
        with store.import_lock(self.data):
            code, _, err = self.update(net)
        self.assertEqual(code, 20)
        self.assertIn("another import is running", err)
        self.assertEqual(net.calls, [])

    def test_a_subtotal_that_is_not_a_number_is_no_crash(self):
        # Review F2: the progress note skips the check instead of raising.
        self.adafruit_only(NEW_ORDERS[:2])
        path = os.path.join(self.data, "adafruit", "current", adafruit.ORDERS_CSV)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(",Shipped,9.90,", ",Shipped,n/a,", 1))
        net = FakeNet(adafruit_routes(*(order_page(o) for o in NEW_ORDERS[:2])))
        code, _, err = self.update(net)
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(self.items_json()), NEW_ORDERS[:2])

    def test_subtotal_mismatch_is_logged(self):
        self.adafruit_only(NEW_ORDERS[:1])
        net = FakeNet(
            adafruit_routes(
                order_page(NEW_ORDERS[0], (("W", "1", "1.00", "1", "1.00"),))
            )
        )
        code, _, err = self.update(net)
        self.assertEqual(code, 0)
        self.assertIn("(items sum 1.00 != subtotal 9.90)", err)

    def test_missing_email_wins_over_a_throttled_store(self):
        # Review F4: 3 needs a person; a retry code would hide it.
        self.data = self.data_dir()
        net = FakeNet(
            {p_hit(a): b"x" * 2000 for a in ("B000TEST03", "B000TEST04", "B0DIGIT002")}
        )
        net.routes[dp("B000TEST02")] = http_error(dp("B000TEST02"), 429)
        code, out, _ = self.update(net, "--amazon-images", "--json")
        self.assertEqual(code, 3)
        doc = json.loads(out)
        self.assertEqual(doc["vendors"][0]["stopped"]["reason"], "throttled")
        self.assertEqual(doc["vendors"][1]["error"]["code"], 3)

    def test_no_export_is_skipped(self):
        self.data = self.data_dir(vendors=())
        code, out, _ = self.update(FakeNet(), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["vendors"], [])

    def test_items_json_is_private(self):
        self.adafruit_only(NEW_ORDERS[:1])
        self.update(FakeNet(adafruit_routes(order_page(NEW_ORDERS[0]))))
        path = os.path.join(self.data, "adafruit", adafruit.ITEMS_JSON)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class ParseItemsTest(support.IsolatedTestCase):
    """The order-status page parser, ported unchanged."""

    def test_two_items_and_their_fields(self):
        page = order_page(
            "1-2",
            (
                ("Board &amp; Case", "11", "1,234.00", "1", "1,234.00"),
                ("Wire", "12", "0.50", "", "0.50"),
            ),
        ).decode()
        items = adafruit.parse_items(page, "1-2")
        self.assertEqual([i["name"] for i in items], ["Board & Case", "Wire"])
        self.assertEqual(items[0]["unit"], "1234.00")
        self.assertEqual(items[1]["qty"], "1")
        self.assertEqual([i["pid"] for i in items], ["11", "12"])

    def test_wrong_page_or_no_items(self):
        with self.assertRaisesRegex(ValueError, "not this order"):
            adafruit.parse_items(order_page("1-2").decode(), "1-3")
        with self.assertRaisesRegex(ValueError, "no item lines"):
            adafruit.parse_items("<h2>Order #1-2</h2>", "1-2")


def p_hit(asin):
    return amazon.P_URL.format(asin=asin)


def dp(asin):
    return amazon.DP_URL.format(asin=asin)


def dp_page(image_id):
    return (
        '<html><script>"hiRes":"https://m.media-amazon.com/images/I/'
        f'{image_id}._AC_SL1500_.jpg"</script></html>'
    ).encode()


class AmazonUpdateTest(UpdateCase):
    """Image lookups: only with --amazon-images, with the old pacing."""

    def setUp(self):
        super().setUp()
        self.data = self.data_dir(vendors=("amazon",))

    def images_json(self):
        path = os.path.join(self.data, "amazon", amazon.IMAGES_JSON)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_no_request_without_the_flag(self):
        # Images are missing (TEST02 awaits phase B; three ASINs are unseen).
        net = FakeNet()
        before = self.images_json()
        code, out, err = self.update(net, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(net.calls, [])
        doc = json.loads(out)
        self.assertEqual(doc["vendors"][0]["store"], "amazon")
        self.assertEqual(doc["vendors"][0]["skipped"], amazon.SKIPPED)
        self.assertEqual(doc["vendors"][0]["requests"], 0)
        self.assertEqual(self.images_json(), before)

    def test_no_request_without_the_flag_with_adafruit_fetching(self):
        os.rename(os.path.join(self.tmp, "data"), os.path.join(self.tmp, "amazon-only"))
        self.data = self.data_dir()
        self.write_email()
        net = FakeNet(adafruit_routes(order_page("1000002-2000000002")))
        code, _, err = self.update(net)
        self.assertEqual(code, 0, err)
        hosts = {urllib.parse.urlsplit(u).hostname for u in net.urls()}
        self.assertEqual(hosts, {"www.adafruit.com"})

    def test_both_phases_with_the_flag(self):
        # Cached: TEST01 (i), TEST02 (tbd), DIGIT001 (p). Unseen: TEST03,
        # TEST04, DIGIT002, probed in phase A; TEST03 is a CDN hit.
        net = FakeNet(
            {
                p_hit("B000TEST03"): b"x" * 2000,
                p_hit("B000TEST04"): b"GIF89a" + b"\0" * 37,
                p_hit("B0DIGIT002"): urllib.error.URLError("timed out"),
                dp("B000TEST02"): dp_page("IMGTWO"),
                dp("B000TEST04"): http_error(dp("B000TEST04"), 404),
                dp("B0DIGIT002"): b"<html>no image here</html>",
            }
        )
        code, out, err = self.update(net, "--amazon-images", "--json")
        self.assertEqual(code, 0, err)
        urls = net.urls()
        self.assertEqual(
            sorted(urls[:3]),
            sorted(p_hit(a) for a in ("B000TEST03", "B000TEST04", "B0DIGIT002")),
        )
        # Phase B, newest order first: TEST02 (2024), TEST04 (2023), DIGIT002 (2021).
        self.assertEqual(
            urls[3:], [dp("B000TEST02"), dp("B000TEST04"), dp("B0DIGIT002")]
        )
        self.assertEqual(
            self.images_json(),
            {
                "B000TEST01": {"id": "TESTIMG01", "src": "i"},
                "B000TEST02": {"id": "IMGTWO", "src": "i"},
                "B000TEST03": {"src": "p"},
                "B000TEST04": {"src": None},
                "B0DIGIT001": {"src": "p"},
                "B0DIGIT002": {"src": None},
            },
        )
        # One wait after each product page: DP_DELAY * (0.75 + random * 0.5).
        self.assertEqual(self.sleeps, [1.5, 1.5, 1.5])
        result = json.loads(out)["vendors"][0]
        self.assertEqual(
            (result["requests"], result["changed"], result["pending"]), (6, 6, 0)
        )
        self.assertIn("IMGTWO", self.page_text())
        for req in net.calls:
            self.assertEqual(req.get_header("User-agent"), amazon.UA)

    def test_captcha_stops_phase_b(self):
        net = FakeNet(
            {
                p_hit("B000TEST03"): b"x" * 2000,
                p_hit("B000TEST04"): b"x" * 2000,
                p_hit("B0DIGIT002"): b"x" * 2000,
                dp("B000TEST02"): b"<html>Robot Check</html>",
            }
        )
        code, out, _ = self.update(net, "--amazon-images", "--json")
        # Phase A saved three entries before the captcha: partial.
        self.assertEqual(code, 21)
        self.assertEqual(net.urls()[3:], [dp("B000TEST02")])
        result = json.loads(out)["vendors"][0]
        self.assertEqual(result["stopped"]["reason"], "throttled")
        self.assertEqual(self.images_json()["B000TEST02"], {"src": "tbd"})
        self.assertEqual(self.images_json()["B000TEST03"], {"src": "p"})

    def test_throttle_before_any_change_exits_20(self):
        images = {a: {"src": "p"} for a in ("B000TEST03", "B000TEST04", "B0DIGIT002")}
        images.update(self.images_json())
        amazon.save_images(os.path.join(self.data, "amazon"), images)
        for answer in (
            http_error(dp("B000TEST02"), 503),
            http_error(dp("B000TEST02"), 429),
            http_error(dp("B000TEST02"), 403),
        ):
            with self.subTest(answer=answer):
                net = FakeNet({dp("B000TEST02"): answer})
                code, _, _ = self.update(net, "--amazon-images")
                self.assertEqual(code, 20)
                self.assertEqual(net.urls(), [dp("B000TEST02")])

    def test_5xx_or_network_error_stops_and_records_nothing(self):
        # Review F1: a transient failure is not "no image"; the ASIN stays tbd.
        images = {a: {"src": "p"} for a in ("B000TEST03", "B000TEST04", "B0DIGIT002")}
        images.update(self.images_json())
        images["B000TEST04"] = {"src": "tbd"}
        amazon.save_images(os.path.join(self.data, "amazon"), images)
        for answer in (
            http_error(dp("B000TEST02"), 500),
            http_error(dp("B000TEST02"), 502),
            urllib.error.URLError("no route"),
            TimeoutError("timed out"),
        ):
            with self.subTest(answer=answer):
                net = FakeNet({dp("B000TEST02"): answer})
                code, out, _ = self.update(net, "--amazon-images", "--json")
                self.assertEqual(code, 20)
                # Stopped at the first page: TEST04 is never asked for.
                self.assertEqual(net.urls(), [dp("B000TEST02")])
                result = json.loads(out)["vendors"][0]
                self.assertEqual(result["stopped"]["reason"], "unreachable")
                self.assertEqual(self.images_json()["B000TEST02"], {"src": "tbd"})
                self.assertEqual(result["pending"], 2)

    def test_nothing_missing_makes_no_requests(self):
        images = {a: {"src": "p"} for a in ("B000TEST03", "B000TEST04", "B0DIGIT002")}
        images.update(self.images_json())
        images["B000TEST02"] = {"src": None}
        amazon.save_images(os.path.join(self.data, "amazon"), images)
        net = FakeNet()
        code, _, err = self.update(net, "--amazon-images")
        self.assertEqual(code, 0, err)
        self.assertEqual(net.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.data, "index.html")))

    def test_dry_run_counts_and_sends_nothing(self):
        net = FakeNet()
        code, out, _ = self.update(net, "--amazon-images", "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(net.calls, [])
        # TEST02 (tbd) and the three unseen ASINs.
        self.assertEqual(json.loads(out)["vendors"][0]["pending"], 4)


class OptionsTest(support.IsolatedTestCase):
    """The defaults never reach the network in tests."""

    def test_default_urlopen_is_blocked_in_tests(self):
        opts = fetching.Options()
        req = urllib.request.Request("https://www.adafruit.com/robots.txt")
        with self.assertRaises(AssertionError):
            opts.urlopen(req, 1)
