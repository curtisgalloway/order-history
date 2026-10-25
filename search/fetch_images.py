# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Resolve product images for every ASIN in the order history.

Two phases, results cached in search/images.json (resumable — re-run any time):

  Phase A: probe the images-na P/<ASIN> CDN endpoint concurrently. It serves a
           1x1 placeholder GIF (~43 bytes) with HTTP 200 when it has no image,
           so we distinguish by body size.  Hit -> {"src": "p"},
           miss -> {"src": "tbd"} (probed, awaiting phase B).
  Phase B: for the misses, fetch the amazon.com/dp/<ASIN> product page (slow,
           rate-limited with jitter) and extract the m.media-amazon.com image
           ID from "hiRes"/data-old-hires.  Hit -> {"src": "i", "id": "<id>"},
           page gone/no image -> {"src": null}.

Stops cleanly if Amazon serves a captcha; run again later to continue.
After running, regenerate the page:  python3 search/build.py

Usage: python3 fetch_images.py [--limit N] [--delay SECONDS]
"""

import argparse
import concurrent.futures
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDERS_CSV = os.path.join(BASE, "Your Amazon Orders", "Order History.csv")
DIGITAL_CSV = os.path.join(BASE, "Your Amazon Orders", "Digital Content Orders.csv")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CAPTCHA_MARKERS = (b"validateCaptcha", b"Robot Check", b"To discuss automated access")
IMG_PATTERNS = (
    re.compile(rb'"hiRes":"https://m\.media-amazon\.com/images/I/([^".]+)\.'),
    re.compile(rb'data-old-hires="https://m\.media-amazon\.com/images/I/([^".]+)\.'),
    re.compile(rb'id="landingImage"[^>]*src="https://m\.media-amazon\.com/images/I/([^".]+)\.'),
)


def load_asins():
    """Unique ASINs, newest order first, so partial runs favor recent items."""
    dated = []
    for path, datecol in ((ORDERS_CSV, "Order Date"), (DIGITAL_CSV, "Order Date")):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                a = r["ASIN"].strip()
                if a and a != "Not Available":
                    dated.append((r[datecol] or "", a))
    dated.sort(reverse=True)
    seen, ordered = set(), []
    for _, a in dated:
        if a not in seen:
            seen.add(a)
            ordered.append(a)
    return ordered


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, CACHE)


def probe_p(asin):
    """True if the P/ CDN endpoint has a real image for this ASIN."""
    url = f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SL160_.jpg"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return len(resp.read()) > 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def scrape_dp(asin):
    """Return ('ok', imageId) | ('none', None) | ('captcha', None)."""
    url = f"https://www.amazon.com/dp/{asin}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "none", None
        if e.code in (429, 503):
            return "captcha", None
        return "none", None
    except (urllib.error.URLError, TimeoutError, OSError):
        return "none", None
    if any(m in body for m in CAPTCHA_MARKERS):
        return "captcha", None
    for pat in IMG_PATTERNS:
        m = pat.search(body)
        if m:
            return "ok", m.group(1).decode()
    return "none", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="max dp pages to scrape this run (0 = no limit)")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="seconds between dp page fetches")
    args = ap.parse_args()

    asins = load_asins()
    cache = load_cache()
    todo = [a for a in asins if a not in cache]
    print(f"{len(asins)} unique ASINs, {len(cache)} cached, {len(todo)} to probe")

    if todo:
        print("phase A: probing P/ CDN endpoint ...")
        done = hits = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for asin, hit in zip(todo, ex.map(probe_p, todo)):
                cache[asin] = {"src": "p"} if hit else {"src": "tbd"}
                hits += hit
                done += 1
                if done % 250 == 0:
                    save_cache(cache)
                    print(f"  probed {done}/{len(todo)}")
        save_cache(cache)
        print(f"  P/ endpoint serves {hits} of {len(todo)} probed")

    misses = [a for a in asins if cache.get(a, {"src": "tbd"})["src"] == "tbd"]
    if args.limit:
        misses = misses[:args.limit]
    print(f"phase B: scraping {len(misses)} product pages "
          f"(~{len(misses) * args.delay / 60:.0f} min) ...")
    scraped = 0
    for asin in misses:
        status, image_id = scrape_dp(asin)
        if status == "captcha":
            save_cache(cache)
            print(f"  captcha/throttle after {scraped} pages — stopping; "
                  "re-run later to continue")
            sys.exit(1)
        cache[asin] = {"src": "i", "id": image_id} if status == "ok" else {"src": None}
        scraped += 1
        if scraped % 25 == 0:
            save_cache(cache)
            print(f"  scraped {scraped}/{len(misses)}")
        time.sleep(args.delay * (0.75 + random.random() * 0.5))
    save_cache(cache)

    counts = {"p": 0, "i": 0, None: 0, "tbd": 0}
    for v in cache.values():
        counts[v["src"]] += 1
    print(f"done: {counts['p']} via P/ CDN, {counts['i']} via product page, "
          f"{counts[None]} unavailable, {counts['tbd']} still to scrape")
    print("now run: python3 search/build.py")


if __name__ == "__main__":
    main()
