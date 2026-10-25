# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Fetch the item lists of your Adafruit orders into Adafruit/items.json.

Adafruit's order-history CSV has totals but no items. Its guest "Order
Status" form (on accounts.adafruit.com/users/sign_in) shows an order's items
given the account email and the full order number, with no login. This
script submits that form once per order and caches the parsed items.

Polite by design:
  - checks robots.txt before fetching and stops if the page is disallowed;
  - one request at a time, at least --delay seconds apart (default 10, plus
    jitter), or longer if robots.txt sets a Crawl-delay;
  - incremental: orders already in the cache are never fetched again;
  - stops at the first HTTP 429/5xx instead of retrying.

The email comes from --email, else $ADAFRUIT_EMAIL, else the first line of
Adafruit/lookup_email.txt (gitignored with the rest of Adafruit/).

  python3 search/fetch_adafruit_items.py && python3 search/build.py

Exit status: 0 done (possibly nothing new), 1 a fetch or parse failed,
2 usage error (no email, no export).
"""

import argparse
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

import build

LOOKUP_URL = "https://www.adafruit.com/index.php?main_page=account_history_info"
ROBOTS_URL = "https://www.adafruit.com/robots.txt"
SITE = "https://www.adafruit.com"
CACHE = os.path.join(build.BASE, "Adafruit", "items.json")
EMAIL_FILE = os.path.join(build.BASE, "Adafruit", "lookup_email.txt")
UA = "order-history-search/1.0 (personal order archive; looks up its own orders)"

ROW_SPLIT = 'confirm-cart mobile-text-wrapper">'
COL_RE = re.compile(r'<div class="col-lg-2[^"]*">(.*?)</div>', re.S)
NAME_COL_RE = re.compile(r'<div class="col-lg-5[^"]*">(.*?)</div>', re.S)
PID_RE = re.compile(r"PID:\s*(\d+)")
IMG_RE = re.compile(r'<img[^>]*\ssrc="([^"]+)"')
HREF_RE = re.compile(r'<a href="([^"]+)"')


def _text(fragment):
    fragment = re.sub(r'<span class="product_id">.*?</span>', "", fragment, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_items(page, order_id):
    """Item lines from an order-status page; raises ValueError if it isn't one."""
    if f"Order #{order_id}" not in page:
        raise ValueError("response is not this order's status page")
    items = []
    for chunk in page.split(ROW_SPLIT)[1:]:
        cols = [_text(c) for c in COL_RE.findall(chunk)[:3]]
        name_col = NAME_COL_RE.search(chunk)
        if len(cols) < 3 or not name_col:
            continue
        price, qty, total = cols
        pid = PID_RE.search(chunk)
        img = IMG_RE.search(chunk)
        href = HREF_RE.search(name_col.group(1))
        item = {
            "name": _text(name_col.group(1)),
            "qty": qty or "1",
            "unit": build.money(price.lstrip("$")),
            "total": build.money(total.lstrip("$")),
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


def fetch(email, order_id):
    body = urllib.parse.urlencode({"email": email, "order_number": order_id}).encode()
    req = urllib.request.Request(LOOKUP_URL, data=body, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def robots_delay(min_delay):
    """Checks robots.txt allows the lookup page; returns the delay to use.

    Fetched with our own User-Agent: RobotFileParser.read() uses Python's
    default one, which Adafruit answers with 403, and the parser then treats
    the whole site as disallowed. Any failure to read robots.txt stops the run.
    """
    req = urllib.request.Request(ROBOTS_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="replace").splitlines()
    except urllib.error.URLError as e:
        sys.exit(f"could not read {ROBOTS_URL} ({e}); not fetching")
    rp = urllib.robotparser.RobotFileParser(ROBOTS_URL)
    rp.parse(lines)
    if not rp.can_fetch(UA, LOOKUP_URL):
        sys.exit(f"robots.txt disallows {LOOKUP_URL}; not fetching")
    return max(min_delay, float(rp.crawl_delay(UA) or 0))


def get_email(arg):
    if arg:
        return arg
    if os.environ.get("ADAFRUIT_EMAIL"):
        return os.environ["ADAFRUIT_EMAIL"]
    if os.path.exists(EMAIL_FILE):
        with open(EMAIL_FILE, encoding="utf-8") as f:
            return f.readline().strip()
    return ""


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    os.replace(tmp, CACHE)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--email", help="Adafruit account email")
    parser.add_argument(
        "--delay", type=float, default=10.0, help="seconds between requests"
    )
    parser.add_argument("--limit", type=int, default=0, help="fetch at most N orders")
    parser.add_argument("--refresh", action="store_true", help="refetch cached orders")
    args = parser.parse_args()

    email = get_email(args.email)
    if not email:
        print("no email: pass --email, set ADAFRUIT_EMAIL, or write it to", EMAIL_FILE)
        sys.exit(2)
    orders = build.load_adafruit(with_items=False)
    if not orders:
        print("no Adafruit export at", build.ADAFRUIT_CSV)
        sys.exit(2)

    cache = load_cache()
    todo = [o for o in orders if args.refresh or o["id"] not in cache]
    print(
        f"{len(orders)} orders, {len(orders) - len(todo)} cached, {len(todo)} to fetch"
    )
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        return

    delay = robots_delay(args.delay)
    failed = 0
    for n, order in enumerate(todo):
        if n:
            time.sleep(delay + random.uniform(0, delay / 2))
        oid = order["id"]
        try:
            items = parse_items(fetch(email, oid), oid)
        except urllib.error.HTTPError as e:
            print(f"  {oid}: HTTP {e.code}")
            if e.code == 429 or e.code >= 500:
                print("  server is busy or limiting; stopping (re-run later)")
                failed += 1
                break
            failed += 1
            continue
        except (urllib.error.URLError, ValueError) as e:
            print(f"  {oid}: {e}")
            failed += 1
            continue
        cache[oid] = {"fetched": time.strftime("%Y-%m-%d"), "items": items}
        save_cache(cache)
        line_sum = sum(float(i["total"]) for i in items if i["total"])
        subtotal = (order["summary"] or {}).get("subtotal", "")
        check = (
            ""
            if not subtotal or abs(line_sum - float(subtotal)) < 0.01
            else (f"  (items sum {line_sum:.2f} != subtotal {subtotal})")
        )
        print(f"  {oid}: {len(items)} items{check}")

    print(f"wrote {CACHE}; now run: python3 search/build.py")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
