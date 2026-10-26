# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Amazon's "Request My Data" export.

Layout under the vendor folder (<data>/amazon/):

  current/Your Amazon Orders/Order History.csv           physical orders
  current/Your Amazon Orders/Digital Content Orders.csv  digital orders
  images.json                                            ASIN -> image cache
  order-pages.json                                       saved orders (saved.py)

Both CSVs have one row per item; rows are grouped into orders by Order ID.

Amazon keeps saved orders (SAVED_ORDERS): orders the agent read from the
signed-in order pages and passed to `order-history add`. load() shows the ones
the export lacks, and enrich() looks up their images like any other.

enrich() fills images.json, and runs only with --amazon-images: it scrapes
amazon.com product pages, which may be against Amazon's conditions of use.
Without the flag it sends no request to any Amazon host. Its two phases and
their pacing are those of the script it replaces (search/fetch_images.py,
removed in M3):

  Phase A: probe the images-na P/<ASIN> CDN endpoint, 8 at a time. It serves a
           1x1 placeholder GIF (~43 bytes) with HTTP 200 when it has no image,
           so a hit is told apart by body size. Hit -> {"src": "p"},
           miss -> {"src": "tbd"} (probed, awaiting phase B).
  Phase B: for the misses, fetch amazon.com/dp/<ASIN> one at a time,
           DP_DELAY seconds apart (with +/-25% jitter), and extract the
           m.media-amazon.com image ID. Hit -> {"src": "i", "id": "<id>"},
           a 404 or other 4xx (page gone) or a page with no image ->
           {"src": null}. A captcha, 403, 429 or 503 stops the run, and so
           (unlike the old script, which recorded them as {"src": null})
           does any other 5xx or a network error; that ASIN stays "tbd" and
           the next update continues from the cache.
"""

import collections
import concurrent.futures
import csv
import json
import os
import re
import urllib.error
import urllib.request
import zipfile

from order_history import fetching, model, saved, store

ID = "amazon"
NAME = "Amazon"
# Shown in the page footer.
SOURCE = "Order History.csv + Digital Content Orders.csv"
# Orders from the order pages are kept until an export has them (saved.py).
SAVED_ORDERS = True

ORDERS_CSV = os.path.join("Your Amazon Orders", "Order History.csv")
DIGITAL_CSV = os.path.join("Your Amazon Orders", "Digital Content Orders.csv")
IMAGES_JSON = "images.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
P_URL = "https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SL160_.jpg"
DP_URL = "https://www.amazon.com/dp/{asin}"
ORDER_URL = "https://www.amazon.com/gp/your-account/order-details?orderID={order_id}"
# What a saved order's ID and ASINs must look like, since both go into links.
ORDER_ID = re.compile(r"[0-9A-Z]{3}-\d{7}-\d{7}")
ASIN = re.compile(r"[0-9A-Z]{10}")
PROBE_WORKERS = 8
PROBE_TIMEOUT = 15
DP_TIMEOUT = 30
DP_DELAY = 2.0  # seconds between product pages, before jitter
# How often a long run saves its progress.
PROBE_SAVE_EVERY = 250
DP_SAVE_EVERY = 25
SKIPPED = "image lookups scrape amazon.com; pass --amazon-images to run them"
CAPTCHA_MARKERS = (b"validateCaptcha", b"Robot Check", b"To discuss automated access")
IMG_PATTERNS = (
    re.compile(rb'"hiRes":"https://m\.media-amazon\.com/images/I/([^".]+)\.'),
    re.compile(rb'data-old-hires="https://m\.media-amazon\.com/images/I/([^".]+)\.'),
    re.compile(
        rb'id="landingImage"[^>]*'
        rb'src="https://m\.media-amazon\.com/images/I/([^".]+)\.'
    ),
)


def detect(path):
    """True for a folder or zip that holds Your Amazon Orders/Order History.csv."""
    if os.path.isdir(path):
        return os.path.isfile(os.path.join(path, ORDERS_CSV))
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            return "Your Amazon Orders/Order History.csv" in z.namelist()
    return False


def install(src, dest):
    """Unpack a zip, or copy a folder, into the empty folder dest."""
    if os.path.isdir(src):
        store.copy_tree(src, dest)
    else:
        store.extract_zip(src, dest)


def _rows(path, digital):
    """Group one Amazon CSV's item rows into orders."""
    orders = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            oid = model.clean(r["Order ID"])
            if digital:
                cur = model.clean(r["Price Currency Code"]) or "USD"
                qty = model.clean(r["Quantity Ordered"])
                total, unit = model.money(r["Price"]), ""
                site = model.clean(r["Marketplace"])
            else:
                cur = model.clean(r["Currency"]) or "USD"
                qty = model.clean(r["Original Quantity"])
                total, unit = model.money(r["Total Amount"]), model.money(
                    r["Unit Price"]
                )
                site = model.clean(r["Website"])
            order = orders.get(oid)
            if order is None:
                order = orders[oid] = model.new_order(
                    ID,
                    oid,
                    model.clean(r["Order Date"])[:10],
                    status=model.status(r["Order Status"]),
                    currency=cur,
                    digital=digital,
                    site=site,
                    url="" if digital or not oid else ORDER_URL.format(order_id=oid),
                )
            asin = model.clean(r["ASIN"])
            order["items"].append(
                model.new_item(
                    model.clean(r["Product Name"]),
                    asin=asin,
                    qty=qty or "1",
                    unit=unit,
                    total=total,
                    url=DP_URL.format(asin=asin) if asin else "",
                    # Exports from late 2026 on; absent in older ones.
                    department=model.clean(r.get("Department")),
                )
            )
    return list(orders.values())


def read(folder):
    """Orders from an export folder alone, without the image cache."""
    orders = []
    for rel, digital in ((ORDERS_CSV, False), (DIGITAL_CSV, True)):
        path = os.path.join(folder, rel)
        if os.path.exists(path):
            orders += _rows(path, digital)
    return orders


def as_of(folder):
    """The newest order date (YYYY-MM-DD) in an export folder, or ""."""
    return max((o["date"] for o in read(folder)), default="")


def load_images(vendor_dir):
    """The image cache, ASIN -> {"src": ..., "id": ...}; {} when absent."""
    path = os.path.join(vendor_dir, IMAGES_JSON)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def saved_order(order):
    """Check and fill Amazon's own fields on an order for `add` (saved.py).

    Gives it the links and site an exported physical order has. Raises
    ValueError for an order ID or ASIN that isn't Amazon's shape.
    """
    order_id = order["id"]
    if not ORDER_ID.fullmatch(order_id):
        raise ValueError(
            f"order ID {order_id!r} is not an Amazon order number like "
            "111-1234567-1234567"
        )
    order["url"] = ORDER_URL.format(order_id=order_id)
    order["site"] = order["site"] or "Amazon.com"
    for item in order["items"]:
        asin = item["asin"]
        if asin and not ASIN.fullmatch(asin):
            raise ValueError(f"ASIN {asin!r} is not 10 letters or digits")
        item["url"] = DP_URL.format(asin=asin) if asin else ""


def load(vendor_dir, with_saved=True):
    """Orders from <vendor_dir>/current/ plus saved orders, with images merged.

    Saved orders whose IDs are in the export are left out: the export wins.
    The saved file is read before the export: an import prunes it only after
    swapping in the export that has its orders, so a read racing an import
    may see an order twice (and drop the saved copy), never lose it.
    with_saved=False reads the export alone (an import's rebuild uses it when
    order-pages.json can't be read).
    """
    pending = saved.read_file(vendor_dir)["orders"] if with_saved else []
    orders = saved.combine(read(os.path.join(vendor_dir, "current")), pending)
    images = load_images(vendor_dir)
    for order in orders:
        for item in order["items"]:
            info = images.get(item["asin"])
            if info and info["src"] == "i":
                item["image"] = info["id"]
            elif info and info["src"] in (None, "tbd"):
                # Known miss on the P/ endpoint: show the placeholder directly.
                item["noImage"] = True
    return orders


def compare(old, new):
    """Item names that changed between two exports (lists from read()).

    Newer exports have renamed some digital titles and blanked others to
    "Not Applicable". Items are matched by order ID and ASIN. Several lines of
    one order can share an ASIN and come back in another order, so a name found
    on both sides is unchanged wherever it sits; only the names left over on
    each side are paired, in export order.
    """
    old_names = _names_by_asin(old)
    renamed, blanked = [], []
    for (order_id, asin), names in sorted(_names_by_asin(new).items()):
        before_left, after_left = _unmatched(old_names.get((order_id, asin), []), names)
        for before, after in zip(before_left, after_left):
            entry = {"order": order_id, "asin": asin, "old": before, "new": after}
            (blanked if after == model.NO_NAME else renamed).append(entry)
    return {"titles_renamed": renamed, "titles_blanked": blanked}


def _unmatched(old, new):
    """The names in `old` and in `new` that the other side lacks, counting repeats."""
    remaining = collections.Counter(new)
    old_left = []
    for name in old:
        if remaining[name]:
            remaining[name] -= 1
        else:
            old_left.append(name)
    taken = collections.Counter(old) - collections.Counter(old_left)
    new_left = []
    for name in new:
        if taken[name]:
            taken[name] -= 1
        else:
            new_left.append(name)
    return old_left, new_left


def _names_by_asin(orders):
    names = {}
    for order in orders:
        for item in order["items"]:
            if item["asin"]:
                names.setdefault((order["id"], item["asin"]), []).append(item["name"])
    return names


def gaps(vendor_dir, orders):
    """Enrichment gaps for status: items whose ASIN has no image lookup yet."""
    images = load_images(vendor_dir)
    missing = {i["asin"] for o in orders for i in o["items"] if i["asin"] not in images}
    missing.discard("")
    return {"images_missing": len(missing)}


# ---- enrich(): product images ---------------------------------------------


def asins_newest_first(orders):
    """Unique ASINs, newest order first, so partial runs favor recent items."""
    dated = sorted(
        ((o["date"], i["asin"]) for o in orders for i in o["items"] if i["asin"]),
        reverse=True,
    )
    seen, ordered = set(), []
    for _, asin in dated:
        if asin not in seen:
            seen.add(asin)
            ordered.append(asin)
    return ordered


def probe_p(opts, asin):
    """True if the P/ CDN endpoint has a real image for this ASIN."""
    req = urllib.request.Request(P_URL.format(asin=asin), headers={"User-Agent": UA})
    try:
        return len(opts.urlopen(req, PROBE_TIMEOUT)) > 500
    except OSError:  # URLError and TimeoutError are OSErrors
        return False


def scrape_dp(opts, asin):
    """("ok", imageId) | ("none", None) | ("captcha", None) | ("error", why).

    "captcha" is a captcha page, 403, 429 or 503: Amazon is refusing or
    limiting this client. "none" is a page that is gone (another 4xx) or
    has no image;
    "error" is a 5xx other than 503 or a network failure, which says nothing
    about the image and must not be cached as "none".
    """
    req = urllib.request.Request(
        DP_URL.format(asin=asin),
        headers={
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        body = opts.urlopen(req, DP_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503):  # 403: how a blocked client is answered
            return "captcha", None
        if e.code >= 500:
            return "error", f"HTTP {e.code}"
        return "none", None  # 404 and other refusals
    except OSError as e:  # URLError, timeouts, http.client errors (http_read)
        return "error", str(e) or type(e).__name__
    if any(m in body for m in CAPTCHA_MARKERS):
        return "captcha", None
    for pat in IMG_PATTERNS:
        m = pat.search(body)
        if m:
            return "ok", m.group(1).decode()
    return "none", None


def save_images(vendor_dir, cache):
    """Write images.json atomically."""
    fetching.write_json(
        os.path.join(vendor_dir, IMAGES_JSON),
        cache,
        separators=(",", ":"),
        sort_keys=True,
    )


def _awaiting_dp(asins, cache):
    return [a for a in asins if cache.get(a, {"src": "tbd"})["src"] == "tbd"]


def enrich(vendor_dir, opts, orders=None):
    """Look up product images for ASINs not yet resolved in images.json.

    Does nothing, and sends no request, unless opts.amazon_images. orders
    is read() of current/ plus the saved orders (both read here when None),
    so saved orders' images are looked up too. Returns a
    fetching.new_result() dict.
    """
    result = fetching.new_result(ID)
    if not opts.amazon_images:
        result["skipped"] = SKIPPED
        return result
    if orders is None:
        orders = saved.merge(vendor_dir, read(os.path.join(vendor_dir, "current")))
    asins = asins_newest_first(orders)
    cache = load_images(vendor_dir)
    todo = [a for a in asins if a not in cache]
    result["pending"] = len(_awaiting_dp(asins, cache))
    if opts.dry_run or not result["pending"]:
        return result
    opts.log(f"amazon: {len(asins)} ASINs, {len(asins) - len(todo)} cached")

    if todo:
        opts.log(f"amazon: phase A: probing the P/ CDN endpoint for {len(todo)}")
        done = hits = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=PROBE_WORKERS) as ex:
            for asin, hit in zip(todo, ex.map(lambda a: probe_p(opts, a), todo)):
                cache[asin] = {"src": "p"} if hit else {"src": "tbd"}
                hits += hit
                done += 1
                if done % PROBE_SAVE_EVERY == 0:
                    save_images(vendor_dir, cache)
                    opts.log(f"  probed {done}/{len(todo)}")
        result["requests"] += len(todo)
        result["changed"] += len(todo)
        save_images(vendor_dir, cache)
        opts.log(f"  the P/ endpoint serves {hits} of {len(todo)}")

    misses = _awaiting_dp(asins, cache)
    if misses:
        opts.log(f"amazon: phase B: scraping {len(misses)} product pages")
    for scraped, asin in enumerate(misses):
        status, image_id = scrape_dp(opts, asin)
        result["requests"] += 1
        if status == "captcha":
            message = (
                f"captcha or throttling after {scraped} pages; stopped "
                "(run update again later)"
            )
            opts.log("  " + message)
            result["stopped"] = {"reason": "throttled", "message": message}
            break
        if status == "error":
            message = (
                f"{asin}: {image_id}; stopped after {scraped} pages, nothing "
                "recorded for it (run update again later)"
            )
            opts.log("  " + message)
            result["stopped"] = {"reason": "unreachable", "message": message}
            break
        cache[asin] = {"src": "i", "id": image_id} if status == "ok" else {"src": None}
        result["changed"] += 1
        if (scraped + 1) % DP_SAVE_EVERY == 0:
            save_images(vendor_dir, cache)
            opts.log(f"  scraped {scraped + 1}/{len(misses)}")
        opts.sleep(DP_DELAY * (0.75 + opts.random() * 0.5))
    save_images(vendor_dir, cache)
    result["pending"] = len(_awaiting_dp(asins, cache))
    return result
