# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Adafruit's account order-history CSV.

Layout under the vendor folder (<data>/adafruit/):

  current/order_history.csv  one row per order, no item lines
  items.json                 order ID -> {"fetched": ..., "items": [...]}
  lookup_email.txt           the account email, for enrich()

The export writes "-" as a space: order IDs come out as "1234567 1234567890"
and dates as "2024 01 31 12:00:00". The loader puts the hyphens back.

The export has no item lines. enrich() gets them from Adafruit's guest "Order
Status" form (on the account sign-in page), which shows an order's items given
the account email and the full order number, with no login. It is polite by
design, with the rules of the fetcher it replaces (search/fetch_adafruit_items.py,
removed in M3):

  - it checks robots.txt, with its own User-Agent, before fetching, and stops
    if the page is disallowed or robots.txt can't be read;
  - one request at a time, at least MIN_DELAY seconds apart plus up to half
    that again of jitter, or longer if robots.txt sets a Crawl-delay;
  - incremental: an order already in items.json is never fetched again;
  - it stops at the first HTTP 429 or 5xx instead of retrying.
"""

import csv
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from order_history import fetching, model

ID = "adafruit"
NAME = "Adafruit"
# Shown in the page footer.
SOURCE = "order_history.csv + items.json"

ORDERS_CSV = "order_history.csv"
ITEMS_JSON = "items.json"
EMAIL_FILE = "lookup_email.txt"
EMAIL_ENV = "ADAFRUIT_EMAIL"

LOOKUP_URL = "https://www.adafruit.com/index.php?main_page=account_history_info"
ROBOTS_URL = "https://www.adafruit.com/robots.txt"
SITE = "https://www.adafruit.com"
# Unchanged from the old fetcher, so robots.txt rules keep matching it.
UA = "order-history-search/1.0 (personal order archive; looks up its own orders)"
MIN_DELAY = 10.0  # seconds between requests, before jitter
TIMEOUT = 30

# Columns the export has always had; detect() needs all of them.
HEADER = {
    "order_id",
    "date_purchased",
    "order_status",
    "subtotal",
    "shipping",
    "tax",
    "coupon",
    "gift_certificate",
    "total",
    "shipping_method",
}


def detect(path):
    """True for a CSV whose header has the export's columns."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f), [])
    except (OSError, UnicodeDecodeError, csv.Error):
        return False
    return HEADER <= {h.strip() for h in header}


def install(src, dest):
    """Copy the CSV into the empty folder dest."""
    shutil.copyfile(src, os.path.join(dest, ORDERS_CSV))


def _text(v):
    """Undo the export's mangling of shipping-method text.

    The export replaces "-" and "=" with spaces and leaves (sometimes
    truncated) HTML in the shipping method.
    """
    v = re.sub(r"<[^>]*>?", "", model.clean(v))
    return re.sub(r"\s+", " ", v).strip()


def _order_id(v):
    return "-".join(model.clean(v).split())


def _date(v):
    return "-".join(model.clean(v).split()[:3])


def _export_rows(folder):
    path = os.path.join(folder, ORDERS_CSV)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def as_of(folder):
    """The newest order date (YYYY-MM-DD) in an export folder, or ""."""
    return max((_date(r["date_purchased"]) for r in _export_rows(folder)), default="")


def load_items(vendor_dir):
    """The item cache written by the item fetcher; {} when absent."""
    path = os.path.join(vendor_dir, ITEMS_JSON)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(folder):
    """Orders from an export folder alone; the export has no item lines."""
    orders = []
    for r in _export_rows(folder):
        discount = model.money(r["coupon"]) or model.money(r["gift_certificate"])
        orders.append(
            model.new_order(
                ID,
                _order_id(r["order_id"]),
                _date(r["date_purchased"]),
                status=model.status(r["order_status"]),
                total=model.money(r["total"]),
                shipMethod=_text(r["shipping_method"]),
                summary={
                    "subtotal": model.money(r["subtotal"]),
                    "shipping": model.money(r["shipping"]),
                    "tax": model.money(r["tax"]),
                    "discount": discount,
                },
            )
        )
    return orders


def load(vendor_dir):
    """Orders from <vendor_dir>/current/, with items.json merged in."""
    fetched = load_items(vendor_dir)
    orders = read(os.path.join(vendor_dir, "current"))
    for order in orders:
        order["items"] = [
            model.new_item(i["name"], **{k: v for k, v in i.items() if k != "name"})
            for i in fetched.get(order["id"], {}).get("items", [])
        ]
    return orders


def gaps(vendor_dir, orders):
    """Enrichment gaps for status: orders whose items haven't been fetched."""
    fetched = load_items(vendor_dir)
    return {"items_unfetched": sum(1 for o in orders if o["id"] not in fetched)}


# ---- enrich(): item lines from the order-status page -----------------------

ROW_SPLIT = 'confirm-cart mobile-text-wrapper">'
COL_RE = re.compile(r'<div class="col-lg-2[^"]*">(.*?)</div>', re.S)
NAME_COL_RE = re.compile(r'<div class="col-lg-5[^"]*">(.*?)</div>', re.S)
PID_RE = re.compile(r"PID:\s*(\d+)")
IMG_RE = re.compile(r'<img[^>]*\ssrc="([^"]+)"')
HREF_RE = re.compile(r'<a href="([^"]+)"')


def _page_text(fragment):
    fragment = re.sub(r'<span class="product_id">.*?</span>', "", fragment, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_items(page, order_id):
    """Item lines from an order-status page; raises ValueError if it isn't one."""
    if f"Order #{order_id}" not in page:
        raise ValueError("response is not this order's status page")
    items = []
    for chunk in page.split(ROW_SPLIT)[1:]:
        cols = [_page_text(c) for c in COL_RE.findall(chunk)[:3]]
        name_col = NAME_COL_RE.search(chunk)
        if len(cols) < 3 or not name_col:
            continue
        price, qty, total = cols
        pid = PID_RE.search(chunk)
        img = IMG_RE.search(chunk)
        href = HREF_RE.search(name_col.group(1))
        item = {
            "name": _page_text(name_col.group(1)),
            "qty": qty or "1",
            "unit": model.money(price.lstrip("$")),
            "total": model.money(total.lstrip("$")),
        }
        if pid:
            item["pid"] = pid.group(1)
        if href:
            item["url"] = urllib.parse.urljoin(SITE, href.group(1))
        if img:
            item["imageUrl"] = img.group(1)
        items.append(item)
    if not items:
        raise ValueError("order page has no item lines")
    return items


def lookup_email(vendor_dir, flag=""):
    """--email, else $ADAFRUIT_EMAIL, else lookup_email.txt's first line, or ""."""
    if flag:
        return flag
    if os.environ.get(EMAIL_ENV):
        return os.environ[EMAIL_ENV]
    path = os.path.join(vendor_dir, EMAIL_FILE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.readline().strip()
    return ""


def _fetch(opts, email, order_id):
    body = urllib.parse.urlencode({"email": email, "order_number": order_id}).encode()
    req = urllib.request.Request(LOOKUP_URL, data=body, headers={"User-Agent": UA})
    return opts.urlopen(req, TIMEOUT).decode("utf-8", errors="replace")


def robots_delay(opts, min_delay=MIN_DELAY):
    """(delay, None) when robots.txt allows the lookup page; else (None, stopped).

    Fetched with our own User-Agent: RobotFileParser.read() uses Python's
    default one, which Adafruit answers with 403, and the parser then treats
    the whole site as disallowed. Any failure to read robots.txt stops the run.
    """
    req = urllib.request.Request(ROBOTS_URL, headers={"User-Agent": UA})
    try:
        body = opts.urlopen(req, TIMEOUT)
    except OSError as e:  # urllib.error.URLError and HTTPError are OSErrors
        return None, {
            "reason": "robots_unreadable",
            "message": f"could not read {ROBOTS_URL} ({e}); not fetching",
        }
    rp = urllib.robotparser.RobotFileParser(ROBOTS_URL)
    rp.parse(body.decode("utf-8", errors="replace").splitlines())
    if not rp.can_fetch(UA, LOOKUP_URL):
        return None, {
            "reason": "robots",
            "message": f"robots.txt disallows {LOOKUP_URL}; not fetching",
        }
    return max(min_delay, float(rp.crawl_delay(UA) or 0)), None


def save_items(vendor_dir, cache):
    """Write items.json atomically."""
    fetching.write_json(
        os.path.join(vendor_dir, ITEMS_JSON), cache, indent=1, sort_keys=True
    )


def _subtotal_check(order, items):
    """A note for the progress log when the item lines don't sum to the subtotal."""
    subtotal = (order["summary"] or {}).get("subtotal", "")
    try:
        line_sum = sum(float(i["total"]) for i in items if i["total"])
        differs = bool(subtotal) and abs(line_sum - float(subtotal)) >= 0.01
    except ValueError:  # model.money() passes a non-number through as it is
        return ""
    if not differs:
        return ""
    return f"  (items sum {line_sum:.2f} != subtotal {subtotal})"


def enrich(vendor_dir, opts, orders=None):
    """Fetch the item lines of every order not yet in items.json.

    orders is read() of current/ (read here when None). Returns a
    fetching.new_result() dict. Raises fetching.EnrichError (exit 3) when
    there are orders to fetch and no lookup email. Makes no request at all
    when nothing is missing, or with opts.dry_run.
    """
    result = fetching.new_result(ID)
    if orders is None:
        orders = read(os.path.join(vendor_dir, "current"))
    cache = load_items(vendor_dir)
    todo = [o for o in orders if o["id"] not in cache]
    result["pending"] = len(todo)
    if not todo or opts.dry_run:
        return result
    email = lookup_email(vendor_dir, opts.email)
    if not email:
        raise fetching.EnrichError(
            f"{len(todo)} Adafruit orders have no item list, and there is no "
            f"lookup email: pass --email, set {EMAIL_ENV}, or write it to "
            + os.path.join(vendor_dir, EMAIL_FILE),
            3,
        )
    cached = len(orders) - len(todo)
    opts.log(f"adafruit: {len(orders)} orders, {cached} cached, {len(todo)} to fetch")

    delay, stopped = robots_delay(opts)
    result["requests"] += 1
    if stopped:
        opts.log("adafruit: " + stopped["message"])
        result["stopped"] = stopped
        return result

    for n, order in enumerate(todo):
        if n:
            opts.sleep(delay + opts.uniform(0, delay / 2))
        oid = order["id"]
        result["requests"] += 1
        try:
            items = parse_items(_fetch(opts, email, oid), oid)
        except urllib.error.HTTPError as e:
            opts.log(f"  {oid}: HTTP {e.code}")
            if e.code == 429 or e.code >= 500:
                message = (
                    f"HTTP {e.code}: the server is busy or limiting; stopped "
                    "(run update again later)"
                )
                opts.log("  " + message)
                result["stopped"] = {"reason": "throttled", "message": message}
                break
            result["failed"].append({"id": oid, "error": f"HTTP {e.code}"})
            continue
        except (OSError, ValueError) as e:
            opts.log(f"  {oid}: {e}")
            result["failed"].append({"id": oid, "error": str(e)})
            continue
        cache[oid] = {"fetched": opts.today.isoformat(), "items": items}
        save_items(vendor_dir, cache)
        result["changed"] += 1
        result["pending"] -= 1
        opts.log(f"  {oid}: {len(items)} items{_subtotal_check(order, items)}")
    return result
