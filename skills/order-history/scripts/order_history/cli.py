# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The order-history command line.

Data goes to stdout and messages to stderr. --json prints one JSON document.
--skill (or the skill command) prints the agent instructions, SKILL.md, with
the version stamped in; `skill <store>` prints that store's instructions.

Exit codes: 0 ok; 1 nothing found; 2 bad usage, or a file no store (or several)
recognizes; 3 no data folder (run init); 4 the page couldn't be built: no
page shell could be found (offline with no cache and no Node) or index.html
couldn't be written; the old page is unchanged, and an import is undone; 20
nothing changed: another import is running (also for build), or a failure was
rolled back, retry; 21 an import's rollback failed, check the folders named;
30 an older export without --force, or an unsafe zip member or folder entry.

skill: 0 printed; 2 an unknown store; 3 a store with no instruction file. It
needs no data folder. --json wraps the text as {store, version, text}; --skill
always prints Markdown. The per-command table is in SKILL.md ("Exit codes").

update: 0 done (possibly nothing to do); 3 also when Adafruit orders need
items and there is no lookup email (this wins over 20 and 21: retrying can't
fix it; --json has each store's result); 20 nothing was fetched: a site
throttled or was unreachable, robots.txt disallows or couldn't be read, every
lookup failed, or another update or an import is running; retry later; 21
some lookups were saved (by any store) before a site stopped the run or
other lookups failed (the caches are partial, the page is rebuilt), or the
page couldn't be rebuilt because an import was running; run update or build
again later; 4 the page couldn't be rebuilt.

add: 0 saved (or a dry run); 2 bad usage, an input that isn't a valid
document (nothing saved), or an unreadable order-pages.json; 3 no data folder,
or no export of that store yet; 4 saved, but the page couldn't be rebuilt (run
build); 20 nothing saved: an import is running, or the file couldn't be
written; retry.
"""

import argparse
import datetime
from importlib import resources
import json
import os
import re
import sys

from order_history import (
    __version__,
    config,
    fetching,
    model,
    page,
    saved,
    search,
    store,
    vendors,
)

EXIT_OK = 0
EXIT_EMPTY = 1
EXIT_USAGE = 2
EXIT_NO_DATA = 3
EXIT_NO_SHELL = page.EXIT_NO_SHELL
EXIT_REFUSED = store.EXIT_REFUSED
EXIT_RETRY_FREE = store.EXIT_RETRY_FREE
EXIT_PARTIAL = store.EXIT_RECONCILE


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


# The skill's documents ship inside the package (symbolic links to
# skills/order-history/SKILL.md and vendors/<id>.md, which a wheel stores as
# files), so --skill always prints the text of the version that runs.
SKILL_RESOURCE = "agent_skill.md"
SKILL_STAMP = "\nPrinted by `order-history --skill`, version {version}.\n"


def _write_text(text):
    """Write text to stdout as UTF-8 bytes, whatever the locale says."""
    out = sys.stdout
    if hasattr(out, "buffer"):
        out.flush()
        out.buffer.write(text.encode("utf-8"))
        out.buffer.flush()
    else:  # a text stream with no bytes underneath (tests)
        out.write(text)


def skill_text():
    """SKILL.md as shipped, with a version line after its frontmatter."""
    text = resources.files("order_history").joinpath(SKILL_RESOURCE)
    text = text.read_text(encoding="utf-8")
    end = 0
    if text.startswith("---\n"):
        end = text.index("\n---\n", 3) + len("\n---\n")
    return text[:end] + SKILL_STAMP.format(version=__version__) + text[end:]


def vendor_doc(vendor_id):
    """vendors/<id>.md as shipped; FileNotFoundError when there is none."""
    doc = resources.files("order_history.vendors").joinpath(vendor_id + ".md")
    return doc.read_text(encoding="utf-8")


class _SkillAction(argparse.Action):
    """--skill: print SKILL.md and exit 0, before any command is parsed.

    Always Markdown, so `--skill > SKILL.md` installs it; `skill --json` wraps it.
    """

    def __init__(self, option_strings, dest, **kwargs):
        kwargs.update(nargs=0, default=argparse.SUPPRESS)
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        _write_text(skill_text())
        parser.exit(EXIT_OK)


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


def _load_all(data_dir, registry, tolerant=False):
    """[(vendor, orders or None when the vendor has no export)].

    An unreadable order-pages.json exits 2, unless tolerant (an import's
    rebuild): then that store's export is loaded alone, with a warning, so
    the saved-orders file can't block an import.
    """
    loaded = []
    for vendor in registry:
        vendor_dir = os.path.join(data_dir, vendor.ID)
        if not os.path.isdir(os.path.join(vendor_dir, "current")):
            loaded.append((vendor, None))
            continue
        try:
            orders = vendor.load(vendor_dir)
        except saved.SavedError as e:
            if not tolerant:
                raise CliError(str(e), e.code) from e
            _log(f"order-history: {e}; the page leaves the saved orders out")
            orders = vendor.load(vendor_dir, with_saved=False)
        loaded.append((vendor, model.finish(orders)))
    return loaded


def _all_orders(loaded):
    orders = [o for _, vendor_orders in loaded for o in vendor_orders or []]
    return model.finish(orders)


def cmd_skill(args, registry):
    """Print SKILL.md, or one store's instructions."""
    if args.store is None:
        text = skill_text()
    else:
        known = [v.ID for v in registry]
        if args.store not in known:
            raise CliError(
                f"unknown store {args.store!r}; known: " + ", ".join(known), EXIT_USAGE
            )
        try:
            text = vendor_doc(args.store)
        except FileNotFoundError as e:
            raise CliError(
                f"no instructions for store {args.store!r}", EXIT_NO_DATA
            ) from e
    if args.json:
        _emit_json({"store": args.store, "version": __version__, "text": text})
    else:
        _write_text(text)
    return EXIT_OK


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
            if saved.supports(vendor):
                entry["saved_orders"] = sum(
                    1 for o in orders if o["source"] == saved.SOURCE
                )
                entry["checked"] = saved.checked(vendor_dir)
                entry["stale"] = saved.is_stale(entry["checked"])
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
        n_saved, checked = e.get("saved_orders"), e.get("checked")
        if n_saved:
            line += f" ({n_saved} saved from order pages)"
        line += f"; {gaps}" if gaps else ""
        if checked:
            line += f"; checked {checked}" + (" (stale)" if e["stale"] else "")
        print(line)
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


def _build_page(data_dir, registry, page_hooks, tolerant=False):
    """Write <data>/index.html from every vendor's current export."""
    loaded = _load_all(data_dir, registry, tolerant)
    result = page.build(data_dir, loaded, **page_hooks)
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
            built.update(_build_page(data_dir, registry, page_hooks or {}, True))
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


def _read_input(name):
    """The text of an add input file, or of stdin for "-"."""
    try:
        if name == "-":
            return sys.stdin.read()
        with open(name, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError) as e:  # ValueError: not UTF-8
        raise CliError(f"can't read {name}: {e}; nothing saved", EXIT_USAGE) from e


def _add_text(report):
    vid, n_saved, page_path = report["store"], report["saved_orders"], report["page"]
    added, replaced = len(report["added"]), len(report["replaced"])
    skipped = len(report["skipped_in_export"])
    counts = f"{added} added, {replaced} replaced, {skipped} already in the export"
    if report["dry_run"]:
        _out(f"{vid}: dry run, nothing saved: {counts}")
    else:
        _out(f"{vid}: {counts}; {n_saved} saved orders")
        _out("page: " + (f"rebuilt {page_path}" if page_path else "unchanged"))


def cmd_add(args, registry, page_hooks=None):
    """Save orders read from a store's order pages, then rebuild the page."""
    data_dir = _data_dir(args)
    try:
        vendor, orders = saved.parse(_read_input(args.file), registry)
    except saved.SavedError as e:
        raise CliError(str(e), e.code) from e

    def rebuild():
        return _build_page(data_dir, registry, page_hooks or {})["path"]

    lock = store.read_lock if args.dry_run else store.import_lock
    try:
        with lock(data_dir):
            report = saved.add(
                data_dir,
                vendor,
                orders,
                dry_run=args.dry_run,
                rebuild=None if args.dry_run else rebuild,
            )
    except (saved.SavedError, store.StoreError) as e:
        raise CliError(str(e), e.code) from e
    except page.PageError as e:
        raise CliError(
            f"{e} The orders were saved; run `order-history build` to retry.", e.code
        ) from e
    if args.json:
        _emit_json(report)
    else:
        _add_text(report)
    return EXIT_OK


def _enrich_all(data_dir, registry, opts):
    """Run every vendor's enrich(); [result], one per vendor with an export.

    The exports are read first, under the import lock (exit 20 while an
    import runs), so no read sees current/ mid-swap; the lookups then run
    without it, so a long run doesn't block imports.
    """
    work = []
    with store.import_lock(data_dir):
        for vendor in registry:
            current = os.path.join(data_dir, vendor.ID, "current")
            if hasattr(vendor, "enrich") and os.path.isdir(current):
                orders = vendor.read(current)
                if saved.supports(vendor):
                    try:
                        orders = saved.merge(os.path.dirname(current), orders)
                    except saved.SavedError as e:
                        raise CliError(str(e), e.code) from e
                work.append((vendor, orders))
    results = []
    for vendor, orders in work:
        vendor_dir = os.path.join(data_dir, vendor.ID)
        try:
            result = vendor.enrich(vendor_dir, opts, orders)
        except fetching.EnrichError as e:
            _log(f"order-history: {vendor.ID}: {e}")
            result = fetching.new_result(vendor.ID)
            result["error"] = {"message": str(e), "code": e.code}
        results.append(result)
    return results


def _update_code(results, changed):
    """The exit code for an update's results (see the module docstring).

    A store's precondition error (3) comes first, since retrying can't fix
    it; then 21 or 20 when any store stopped early or had failed lookups.
    """
    errors = [r["error"]["code"] for r in results if r["error"]]
    if errors:
        return errors[0]
    if any(r["stopped"] or r["failed"] for r in results):
        return EXIT_PARTIAL if changed else EXIT_RETRY_FREE
    return EXIT_OK


def _update_text(results, dry_run, page_path):
    for r in results:
        vid, skipped, error, stopped = (
            r["store"],
            r["skipped"],
            r["error"],
            r["stopped"],
        )
        if skipped:
            _out(f"{vid}: skipped ({skipped})")
            continue
        if error:
            _out(f"{vid}: not run: " + error["message"])
            continue
        pending, changed, requests = r["pending"], r["changed"], r["requests"]
        if dry_run:
            _out(f"{vid}: {pending} lookups to make; dry run, nothing fetched")
            continue
        n_failed = len(r["failed"])
        _out(
            f"{vid}: {changed} saved, {n_failed} failed, {pending} still missing, "
            f"{requests} requests"
        )
        if stopped:
            _out(f"{vid}: stopped: " + stopped["message"])
    _out("page: " + (f"rebuilt {page_path}" if page_path else "unchanged"))


def cmd_update(args, registry, page_hooks=None, fetch_hooks=None):
    """Fill the vendors' caches (Adafruit items; Amazon images with the flag)."""
    data_dir = _data_dir(args)
    opts = fetching.Options(
        email=args.email or "",
        amazon_images=args.amazon_images,
        dry_run=args.dry_run,
        **{"log": _log, **(fetch_hooks or {})},
    )
    try:
        with store.update_lock(data_dir):
            results = _enrich_all(data_dir, registry, opts)
    except store.StoreError as e:
        raise CliError(str(e), e.code) from e
    changed = sum(r["changed"] for r in results)
    page_path = None
    if changed:
        try:
            with store.import_lock(data_dir):
                page_path = _build_page(data_dir, registry, page_hooks or {})["path"]
        except page.PageError as e:
            raise CliError(
                f"{e} The caches were updated; run `order-history build` to retry.",
                e.code,
            ) from e
        except store.StoreError as e:
            raise CliError(
                f"{e}. The caches were updated but the page wasn't rebuilt; run "
                "`order-history build` when the import finishes.",
                EXIT_PARTIAL,
            ) from e
    if args.json:
        _emit_json(
            {
                "dry_run": args.dry_run,
                "vendors": results,
                "changed": changed,
                "page": page_path,
            }
        )
    else:
        _update_text(results, args.dry_run, page_path)
    return _update_code(results, changed)


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
    parser.add_argument(
        "--skill",
        action=_SkillAction,
        help="print the agent instructions (SKILL.md) and exit",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser(
        "skill",
        parents=[common],
        help="print the agent instructions",
        description="Print SKILL.md (as --skill does), or with a store ID that"
        " store's instructions: how to get its export, and its quirks.",
    )
    p.add_argument("store", nargs="?", help="a store ID, such as amazon")
    p.set_defaults(func=cmd_skill)
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
        "add",
        parents=[common],
        help="save orders read from a store's order pages",
        description="Save orders newer than the export, read from the store's own"
        ' order pages, from a JSON document: {"store": "amazon", "orders":'
        " [...]}. They show like exported orders until an export contains them."
        " An order already in the export is skipped; one already saved is"
        " replaced. Then rebuild the page.",
    )
    p.add_argument("file", help="the JSON document, or - for stdin")
    p.add_argument(
        "--dry-run", action="store_true", help="report what would change; save nothing"
    )
    p.set_defaults(func=cmd_add)
    p = sub.add_parser(
        "build",
        parents=[common],
        help="rebuild the page",
        description="Write <data>/index.html from the current exports. Needs a page"
        " shell: cached, built locally with npm, or downloaded once from the"
        " release.",
    )
    p.set_defaults(func=cmd_build)
    p = sub.add_parser(
        "update",
        parents=[common],
        help="fetch Adafruit item lists (and Amazon images) and rebuild",
        description="Fill in what the exports leave out, then rebuild the page:"
        " Adafruit item lists, from Adafruit's order-status page (robots.txt"
        " checked, at least 10 s between requests, stops when throttled), and"
        " with --amazon-images, product images scraped from amazon.com. Fetches"
        " only what is missing; with nothing missing it makes no request.",
    )
    p.add_argument(
        "--email",
        help="Adafruit account email (else $ADAFRUIT_EMAIL, else"
        " <data>/adafruit/lookup_email.txt)",
    )
    p.add_argument(
        "--amazon-images",
        action="store_true",
        help="also scrape amazon.com for product images (may be against"
        " Amazon's conditions of use; off by default)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report how many lookups are missing; send no request",
    )
    p.set_defaults(func=cmd_update)
    return parser


def main(argv=None, registry=None, page_hooks=None, fetch_hooks=None):
    """Run the CLI; returns the exit code.

    page_hooks (tests only) go to page.build(): cache, web_dir, build, fetch.
    fetch_hooks (tests only) go to fetching.Options: urlopen, sleep, uniform,
    random, log, today.
    """
    args = build_parser().parse_args(argv)
    args.data_dir = getattr(args, "data_dir", None)
    args.json = getattr(args, "json", False)
    try:
        registry = vendors.VENDORS if registry is None else registry
        if args.func is cmd_update:
            return cmd_update(args, registry, page_hooks, fetch_hooks)
        if args.func in (cmd_add, cmd_build, cmd_import):
            return args.func(args, registry, page_hooks)
        return args.func(args, registry)
    except CliError as e:
        _log(f"order-history: {e}")
        return e.code
