# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The order-history command line.

Data goes to stdout and messages to stderr. --json prints one JSON document.

Exit codes: 0 ok; 1 nothing found; 2 bad usage, or a file no store (or several)
recognizes; 3 no data folder (run init); 4 the page couldn't be built: no
page shell could be found (offline with no cache and no Node) or index.html
couldn't be written; the old page is unchanged, and an import is undone; 20
nothing changed: another import is running (also for build), or a failure was
rolled back, retry; 21 an import's rollback failed, check the folders named;
30 an older export without --force, or an unsafe zip member or folder entry.
"""

import argparse
import datetime
import json
import os
import re
import sys

from order_history import __version__, config, model, page, search, store, vendors

EXIT_OK = 0
EXIT_EMPTY = 1
EXIT_USAGE = 2
EXIT_NO_DATA = 3
EXIT_NO_SHELL = page.EXIT_NO_SHELL
EXIT_REFUSED = store.EXIT_REFUSED


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
    running = store.import_running(data_dir)
    report = []
    for vendor, orders in _load_all(data_dir, registry):
        entry = {"id": vendor.ID, "name": vendor.NAME}
        vendor_dir = os.path.join(data_dir, vendor.ID)
        if orders is None:
            entry["status"] = "missing"
        else:
            entry["status"] = "ok"
            entry["as_of"] = vendor.as_of(os.path.join(vendor_dir, "current"))
            entry["orders"] = len(orders)
            entry["items"] = sum(len(o["items"]) for o in orders)
            if hasattr(vendor, "gaps"):
                entry["gaps"] = vendor.gaps(vendor_dir, orders)
        leftover = store.leftover_staging(vendor_dir)
        if leftover and not running:  # while an import runs, its staging is live
            entry["leftover_staging"] = leftover
        marker = store.reconcile_marker(vendor_dir)
        if marker:
            entry["import_failed"] = marker
        report.append(entry)
    page_path = os.path.join(data_dir, page.PAGE_NAME)
    built = (
        datetime.datetime.fromtimestamp(os.path.getmtime(page_path))
        .astimezone()
        .isoformat(timespec="seconds")
        if os.path.exists(page_path)
        else None
    )
    if args.json:
        _emit_json(
            {
                "data_dir": data_dir,
                "vendors": report,
                "page_built": built,
                "import_running": running,
            }
        )
        return EXIT_OK
    print(f"data folder: {data_dir}")
    if running:
        print("an import is running")
    for e in report:
        if e.get("import_failed"):
            _out(
                e["id"]
                + ": an import failed and couldn't undo itself; see "
                + e["import_failed"]
            )
        if e.get("leftover_staging"):
            n = len(e["leftover_staging"])
            _out(
                e["id"] + f": {n} staging folder(s) left by an interrupted import; "
                "the next import of this store removes them"
            )
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


def _import_text(report):
    """The short text summary of an import report; --json has the lists."""
    vid, as_of = report["store"], report["as_of"]
    new_date, old_date = as_of["new"] or "undated", as_of["old"]
    was = f"; current one as of {old_date}" if old_date else ""
    head = {
        "imported": "imported",
        "dry_run": "dry run, nothing changed:",
        "refused_older": "not imported:",
    }[report["action"]]
    _out(f"{vid}: {head} export as of {new_date}{was}")
    for key in ("orders", "items"):
        part = report[key]
        n_added, n_removed = len(part["added"]), len(part["removed"])
        after, before = part["after"], part["before"]
        _out(
            f"  {key}: {after} (was {before}), " f"{n_added} added, {n_removed} removed"
        )
    for name, entries in report["findings"].items():
        if entries:
            _out("  " + name.replace("_", " ") + f": {len(entries)}")
    archived = report["archived_to"]
    if archived:
        _out(f"  previous export archived to {archived}")
    for name in report["removed_staging"]:
        _out(f"  removed {name}, left by an interrupted import")


def _build_page(data_dir, registry, page_hooks):
    """Write <data>/index.html from every vendor's current export."""
    result = page.build(data_dir, _load_all(data_dir, registry), **page_hooks)
    path, n_orders, shell = result["path"], result["orders"], result["shell"]
    _log(f"wrote {path} ({n_orders} orders; page shell from {shell})")
    return result


def cmd_build(args, registry, page_hooks=None):
    """Rebuild the page from the current exports."""
    data_dir = _data_dir(args)
    try:
        # The import lock: a build must not read current/ mid-swap, nor
        # overwrite the page an import has just written with older data.
        with store.import_lock(data_dir):
            result = _build_page(data_dir, registry, page_hooks or {})
    except page.PageError as e:
        raise CliError(str(e), e.code) from e
    except store.StoreError as e:
        raise CliError(str(e), e.code) from e
    if args.json:
        _emit_json(result)
    else:
        print(result["path"])
    return EXIT_OK


def cmd_import(args, registry, page_hooks=None):
    """Install an export (zip, CSV or folder), archiving the current one."""
    data_dir = _data_dir(args)
    built = {}

    def rebuild():
        # Runs after the swap; a failure here undoes the import (store.py).
        try:
            built.update(_build_page(data_dir, registry, page_hooks or {}))
        except page.PageError as e:
            raise store.StoreError(str(e), e.code) from e

    try:
        report = store.import_export(
            data_dir,
            args.path,
            registry,
            dry_run=args.dry_run,
            force=args.force,
            rebuild=rebuild,
        )
    except store.StoreError as e:
        raise CliError(str(e), e.code) from e
    except OSError as e:
        # Setting up the import (the vendor folder, the lock, staging) failed
        # before the current export was touched.
        raise CliError(f"import failed: {e}; nothing changed", EXIT_USAGE) from e
    report["page"] = built.get("path")
    if args.json:
        _emit_json(report)
    else:
        _import_text(report)
    if report["action"] == "refused_older":
        _log(
            f"order-history: {args.path} is older than the current export; "
            "pass --force to import it anyway"
        )
        return EXIT_REFUSED
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
    p = sub.add_parser(
        "import",
        parents=[common],
        help="install a downloaded export",
        description="Install a store's export (a zip, a CSV or an unzipped folder),"
        " archiving the current one, and report what changed.",
    )
    p.add_argument("path", help="the export: a zip, a CSV or a folder")
    p.add_argument(
        "--dry-run", action="store_true", help="report the changes; change nothing"
    )
    p.add_argument(
        "--force", action="store_true", help="import an export older than the current"
    )
    p.set_defaults(func=cmd_import)
    p = sub.add_parser(
        "build",
        parents=[common],
        help="rebuild the page",
        description="Write <data>/index.html from the current exports. Needs a page"
        " shell: cached, built locally with npm, or downloaded once from the"
        " release.",
    )
    p.set_defaults(func=cmd_build)
    return parser


def main(argv=None, registry=None, page_hooks=None):
    """Run the CLI; returns the exit code.

    page_hooks (tests only) go to page.build(): cache, web_dir, build, fetch.
    """
    args = build_parser().parse_args(argv)
    args.data_dir = getattr(args, "data_dir", None)
    args.json = getattr(args, "json", False)
    try:
        registry = vendors.VENDORS if registry is None else registry
        if args.func in (cmd_build, cmd_import):
            return args.func(args, registry, page_hooks)
        return args.func(args, registry)
    except CliError as e:
        _log(f"order-history: {e}")
        return e.code
