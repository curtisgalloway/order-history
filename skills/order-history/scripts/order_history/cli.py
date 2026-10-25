# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The order-history command line.

Data goes to stdout and messages to stderr. --json prints one JSON document.

Exit codes: 0 ok; 1 nothing found; 2 bad usage; 3 no data folder (run init).
"""

import argparse
import datetime
import json
import os
import re
import sys

from order_history import __version__, config, model, search, vendors

EXIT_OK = 0
EXIT_EMPTY = 1
EXIT_USAGE = 2
EXIT_NO_DATA = 3


class CliError(Exception):
    """A failure to report on stderr and exit with `code`."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


# C0 and C1 control characters; text output replaces them so that a field
# holding terminal escapes can't act on the terminal. --json escapes them.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")


def _safe(text):
    return _CONTROL.sub("?", text)


def _out(line):
    print(_safe(line))


def _log(msg):
    print(_safe(msg), file=sys.stderr)


def _emit_json(doc):
    json.dump(doc, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _data_dir(args):
    """The data folder, which must exist; exits 3 naming init otherwise."""
    try:
        path, source = config.resolve(args.data_dir)
    except config.ConfigError as e:
        raise CliError(str(e), EXIT_USAGE) from e
    if not os.path.isdir(path):
        raise CliError(
            f"no data folder at {path} (from {source}); "
            "run `order-history init` to create one",
            EXIT_NO_DATA,
        )
    return path


def _load_all(data_dir, registry):
    """[(vendor, orders or None when the vendor has no export)]."""
    loaded = []
    for vendor in registry:
        vendor_dir = os.path.join(data_dir, vendor.ID)
        if not os.path.isdir(os.path.join(vendor_dir, "current")):
            loaded.append((vendor, None))
            continue
        loaded.append((vendor, model.finish(vendor.load(vendor_dir))))
    return loaded


def _all_orders(loaded):
    orders = [o for _, vendor_orders in loaded for o in vendor_orders or []]
    return model.finish(orders)


def cmd_init(args, registry):
    """Create the data folder and record it in the config file."""
    del registry  # init needs no vendors
    try:
        path, created, cfg = config.init(args.data_dir)
    except config.ConfigError as e:
        raise CliError(str(e), EXIT_USAGE) from e
    if args.json:
        _emit_json({"data_dir": path, "created": created, "config": cfg})
    else:
        print(path)
        verb = "created" if created else "using existing"
        _log(f"{verb} {path}; recorded in {cfg}")
    return EXIT_OK


def cmd_status(args, registry):
    """Per vendor: as-of date, counts and enrichment gaps; and the page."""
    data_dir = _data_dir(args)
    report = []
    for vendor, orders in _load_all(data_dir, registry):
        entry = {"id": vendor.ID, "name": vendor.NAME}
        if orders is None:
            entry["status"] = "missing"
        else:
            vendor_dir = os.path.join(data_dir, vendor.ID)
            entry["status"] = "ok"
            entry["as_of"] = vendor.as_of(os.path.join(vendor_dir, "current"))
            entry["orders"] = len(orders)
            entry["items"] = sum(len(o["items"]) for o in orders)
            if hasattr(vendor, "gaps"):
                entry["gaps"] = vendor.gaps(vendor_dir, orders)
        report.append(entry)
    page = os.path.join(data_dir, "index.html")
    built = (
        datetime.datetime.fromtimestamp(os.path.getmtime(page))
        .astimezone()
        .isoformat(timespec="seconds")
        if os.path.exists(page)
        else None
    )
    if args.json:
        _emit_json({"data_dir": data_dir, "vendors": report, "page_built": built})
        return EXIT_OK
    print(f"data folder: {data_dir}")
    for e in report:
        if e["status"] == "missing":
            print(e["id"] + ": missing (no export imported)")
            continue
        gaps = ", ".join(
            k.replace("_", " ") + f" {v}" for k, v in e.get("gaps", {}).items()
        )
        vid, as_of, n_orders, n_items = e["id"], e["as_of"], e["orders"], e["items"]
        line = f"{vid}: as of {as_of}, {n_orders} orders, {n_items} items"
        print(line + (f"; {gaps}" if gaps else ""))
    print("page: " + (f"built {built}" if built else "not built"))
    return EXIT_OK


def _item_line(order, item):
    # An item without a total shows none, as on the page (Rows.tsx).
    total = item["total"] if item else order["total"]
    name = item["name"] if item else "(item list not in export)"
    money = f"{total} " + order["currency"] if total else "-"
    return "  ".join([order["date"], order["store"], order["id"], money, name])


def cmd_search(args, registry):
    """Every item matching all the terms, grouped by order, newest first."""
    data_dir = _data_dir(args)
    terms = search.parse_terms(" ".join(args.terms))
    names = {v.ID: v.NAME for v in registry}
    if args.store and args.store not in names:
        raise CliError(
            f"unknown store {args.store!r}; known: " + ", ".join(names), EXIT_USAGE
        )
    orders = _all_orders(_load_all(data_dir, registry))
    results = search.search(orders, terms, names, store=args.store, kind=args.kind)
    if args.json:
        _emit_json(
            {
                "terms": terms,
                "empty": not results,
                "orders": [model.compact(o) for o in results],
            }
        )
    else:
        for order in results:
            for item in order["items"] or [None]:
                _out(_item_line(order, item))
        _log(f"{len(results)} matching orders")
    return EXIT_OK if results else EXIT_EMPTY


def cmd_order(args, registry):
    """One order by its ID."""
    data_dir = _data_dir(args)
    known = [v.ID for v in registry]
    if args.store and args.store not in known:
        raise CliError(
            f"unknown store {args.store!r}; known: " + ", ".join(known), EXIT_USAGE
        )
    orders = _all_orders(_load_all(data_dir, registry))
    found = [
        o
        for o in orders
        if o["id"] == args.id and (not args.store or o["store"] == args.store)
    ]
    if not found:
        _log(f"no order {args.id}")
        if args.json:
            _emit_json({"id": args.id, "empty": True, "order": None})
        return EXIT_EMPTY
    if len(found) > 1:
        stores = sorted({o["store"] for o in found})
        hint = (
            "pass --store"
            if len(stores) > 1
            else f"use `order-history search {args.id}` to see them"
        )
        where = ", ".join(stores)
        raise CliError(
            f"{len(found)} orders have ID {args.id} ({where}); {hint}", EXIT_USAGE
        )
    order = found[0]
    if args.json:
        _emit_json({"id": args.id, "empty": False, "order": model.compact(order)})
        return EXIT_OK
    _out(order["store"] + " order " + order["id"] + ", " + order["date"])
    for key in ("status", "total", "currency", "site", "shipMethod", "url"):
        if order[key]:
            _out(f"  {key}: {order[key]}")
    for item in order["items"] or [None]:
        if item is None:
            print("  (item list not in export)")
            continue
        price = item["total"] or item["unit"]
        line = "  - " + item["qty"] + " x " + item["name"]
        _out(line + (f"  {price}" if price else ""))
    return EXIT_OK


def build_parser():
    """The argument parser; --data-dir and --json work before or after the command."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir", default=argparse.SUPPRESS, help="data folder (overrides all)"
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print one JSON document",
    )
    parser = argparse.ArgumentParser(
        prog="order-history",
        description="Search your own order history from store exports.",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("init", parents=[common], help="create the data folder")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("status", parents=[common], help="what is imported")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("search", parents=[common], help="find items")
    p.add_argument("terms", nargs="+", help="every term must match")
    p.add_argument("--store", help="limit to one store ID")
    p.add_argument("--kind", choices=["physical", "digital"])
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("order", parents=[common], help="show one order")
    p.add_argument("id", help="order ID")
    p.add_argument("--store", help="store ID, when the ID is in several stores")
    p.set_defaults(func=cmd_order)
    return parser


def main(argv=None, registry=None):
    """Run the CLI; returns the exit code."""
    args = build_parser().parse_args(argv)
    args.data_dir = getattr(args, "data_dir", None)
    args.json = getattr(args, "json", False)
    try:
        return args.func(args, vendors.VENDORS if registry is None else registry)
    except CliError as e:
        _log(f"order-history: {e}")
        return e.code
