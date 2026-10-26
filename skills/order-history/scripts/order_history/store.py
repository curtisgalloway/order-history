# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Importing an export: detect, stage, compare, archive, swap (design R3, R4).

The import flow, for the one vendor whose detect() claims the file:

  1. install the export into <vendor>/.staging-<time>-<random>/
  2. read the staged export and current/, and compare them
  3. stop here for --dry-run (staged in a temporary folder outside the data
     folder instead), or when the export is older than current/ without force
  4. rename current/ to archive/<old as_of>/
  5. rename the staging folder to current/
  6. rebuild (a hook: the CLI writes the page)

If 5 or 6 fails, the renames are undone, so the previous export (if there
was one) is current again. If undoing them fails too, nothing is removed: the
staging folder is kept, <vendor>/IMPORT-FAILED.txt says where everything is,
and imports of that store refuse to run until the user deletes it.

What the tool may remove is deliberately narrow: only staging folders it
created, which hold a copy of a file the user still has. It never deletes
current/ or anything in archive/, and it only moves current/ by renaming it
into archive/ under a name that doesn't exist yet.
"""

import contextlib
import datetime
import os
import re
import shutil
import stat
import tempfile
import zipfile

from order_history import model, saved

try:
    import fcntl
except ImportError:  # Windows: no lock (Windows is not a goal, design A1)
    fcntl = None

# Exit codes the CLI uses for these failures (design "Exit codes", and the
# house CLI conventions for the cases the design's table leaves open).
EXIT_UNRECOGNIZED = 2  # no vendor or several claim it, or it can't be read
EXIT_RETRY_FREE = 20  # nothing changed: another import is running, or rolled back
EXIT_RECONCILE = 21  # a rollback failed; folders need checking by hand
EXIT_REFUSED = 30  # an unsafe zip member or folder entry

STAGING_PREFIX = ".staging-"
LOCK_NAME = ".import.lock"
# Held by update while it fills the caches, so two updates can't both
# rewrite items.json or images.json. Imports don't touch the caches.
UPDATE_LOCK_NAME = ".update.lock"
# Written into <vendor>/ when a rollback fails; imports of that store stop
# until the user has put the folders right and deleted it.
RECONCILE_NAME = "IMPORT-FAILED.txt"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Errors that reading or unpacking a damaged or unexpected export can raise.
_READ_ERRORS = (
    OSError,
    ValueError,  # includes UnicodeDecodeError and csv's field-size errors
    KeyError,  # a column the loader needs is missing
    zipfile.BadZipFile,
    RuntimeError,  # an encrypted zip member
    NotImplementedError,  # an unsupported zip compression method
    EOFError,
)


class StoreError(Exception):
    """An import that stopped; `code` is the exit code to use."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


# ---- unpacking ----------------------------------------------------------


def _member_parts(name):
    """The path components of a zip member name; refuses unsafe names."""
    if name.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", name):
        raise StoreError(f"zip member {name!r} has an absolute path", EXIT_REFUSED)
    parts = [p for p in re.split(r"[/\\]", name) if p not in ("", ".")]
    if ".." in parts:
        raise StoreError(f"zip member {name!r} leads outside the folder", EXIT_REFUSED)
    return parts


def check_zip(z):
    """[(info, parts)] for every member; refuses the zip if any is unsafe.

    Unsafe: an absolute path, a ".." component, a symbolic link or other
    special file, or a name that appears twice. Every member is checked
    before anything is written.
    """
    members, seen = [], set()
    for info in z.infolist():
        parts = _member_parts(info.filename)
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            what = "a symbolic link" if kind == stat.S_IFLNK else "a special file"
            raise StoreError(f"zip member {info.filename!r} is {what}", EXIT_REFUSED)
        if not parts:
            continue  # "./" and the like: nothing to create
        key = "/".join(parts)
        if not info.is_dir():
            if key in seen:
                raise StoreError(
                    f"zip member {info.filename!r} appears twice", EXIT_REFUSED
                )
            seen.add(key)
        members.append((info, parts))
    return members


def _inside(root, path):
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def extract_zip(src, dest):
    """Unpack the zip src into the empty folder dest, refusing unsafe members.

    Files are created exclusively, so nothing that exists is overwritten.
    """
    root = os.path.realpath(dest)
    with zipfile.ZipFile(src) as z:
        for info, parts in check_zip(z):
            target = os.path.join(root, *parts)
            if not _inside(root, target):  # cannot happen after check_zip
                raise StoreError(
                    f"zip member {info.filename!r} leads outside the folder",
                    EXIT_REFUSED,
                )
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as fin, open(target, "xb") as fout:
                shutil.copyfileobj(fin, fout)


def copy_tree(src, dest):
    """Copy the folder src into the empty folder dest.

    Refuses, before copying anything, a folder holding a symbolic link or a
    special file, and a dest inside src.
    """
    src_real, dest_real = os.path.realpath(src), os.path.realpath(dest)
    if os.path.commonpath([src_real, dest_real]) == src_real:
        raise StoreError(
            f"can't import {src}: it contains the data folder", EXIT_UNRECOGNIZED
        )
    for root, dirs, files in os.walk(src):
        for name in dirs + files:
            path = os.path.join(root, name)
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                raise StoreError(f"{path} is a symbolic link", EXIT_REFUSED)
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise StoreError(f"{path} is a special file", EXIT_REFUSED)
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = dest if rel == "." else os.path.join(dest, rel)
        os.makedirs(out, exist_ok=True)
        for name in files:
            path = os.path.join(root, name)
            with (
                _open_regular(path) as fin,
                open(os.path.join(out, name), "xb") as fout,
            ):
                shutil.copyfileobj(fin, fout)


def _open_regular(path):
    """Open path for reading, refusing a symbolic link or special file.

    The check and the open are one operation (O_NOFOLLOW, then fstat), so a
    file swapped for a link after copy_tree's first walk is still refused.
    """
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as e:
        if os.path.islink(path):
            raise StoreError(f"{path} is a symbolic link", EXIT_REFUSED) from e
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise StoreError(f"{path} is a special file", EXIT_REFUSED)
    return os.fdopen(fd, "rb")


# ---- comparison (R4) ----------------------------------------------------


def _item_key(order, item):
    return (order["id"], item["asin"] or item["name"])


def _items_by_key(orders):
    by_key = {}
    for order in orders:
        for item in order["items"]:
            by_key.setdefault(_item_key(order, item), []).append(item)
    return by_key


def _item_entry(key, item):
    return {"order": key[0], "asin": item["asin"], "name": item["name"]}


def compare(vendor, old, new):
    """The comparison report's orders, items and vendor findings.

    old and new are read() lists. Orders are matched by ID. Item rows are
    matched by order ID and ASIN (or name, without an ASIN), counting repeats,
    so a renamed item is not reported as removed and added.
    """
    old_ids = {o["id"] for o in old}
    new_ids = {o["id"] for o in new}
    old_items, new_items = _items_by_key(old), _items_by_key(new)
    added, removed = [], []
    for key in sorted(set(old_items) | set(new_items)):
        before, after = old_items.get(key, []), new_items.get(key, [])
        added += [_item_entry(key, i) for i in after[len(before) :]]
        removed += [_item_entry(key, i) for i in before[len(after) :]]
    findings = vendor.compare(old, new) if hasattr(vendor, "compare") else {}
    return {
        "orders": {
            "before": len(old),
            "after": len(new),
            "added": sorted(new_ids - old_ids),
            "removed": sorted(old_ids - new_ids),
        },
        "items": {
            "before": sum(len(o["items"]) for o in old),
            "after": sum(len(o["items"]) for o in new),
            "added": added,
            "removed": removed,
        },
        "findings": findings,
    }


# ---- the data folder ----------------------------------------------------


def leftover_staging(vendor_dir):
    """Names of staging folders an interrupted import left in vendor_dir."""
    if not os.path.isdir(vendor_dir):
        return []
    return sorted(
        name
        for name in os.listdir(vendor_dir)
        if name.startswith(STAGING_PREFIX)
        and not os.path.islink(os.path.join(vendor_dir, name))
        and os.path.isdir(os.path.join(vendor_dir, name))
    )


@contextlib.contextmanager
def _lock(data_dir, name=LOCK_NAME, what="import"):
    """Holds <data>/.import.lock so two imports can't swap at once.

    The lock file stays; removing it would race with the next import.
    """
    fd = os.open(os.path.join(data_dir, name), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise StoreError(
                    f"another {what} is running; try again when it finishes",
                    EXIT_RETRY_FREE,
                ) from e
        yield
    finally:
        os.close(fd)


def import_lock(data_dir):
    """The import lock, for other writers of the data folder (the page build).

    Raises StoreError (exit 20) at once if an import holds it.
    """
    return _lock(data_dir)


def read_lock(data_dir):
    """The shared import lock for a read-only run (a dry run).

    Creates nothing and waits for no one; StoreError (exit 20) mid-import.
    """
    return _shared_lock(data_dir)


def update_lock(data_dir):
    """The update lock (<data>/.update.lock); StoreError (exit 20) if held."""
    return _lock(data_dir, UPDATE_LOCK_NAME, "update")


def import_running(data_dir):
    """True while another process holds the import lock."""
    if fcntl is None:
        return False
    try:
        fd = os.open(os.path.join(data_dir, LOCK_NAME), os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


@contextlib.contextmanager
def _shared_lock(data_dir):
    """For --dry-run: creates nothing, waits for no one, refuses mid-import."""
    fd = None
    if fcntl is not None:
        with contextlib.suppress(FileNotFoundError):
            fd = os.open(os.path.join(data_dir, LOCK_NAME), os.O_RDONLY)
    try:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise StoreError(
                    "another import is running; try again when it finishes",
                    EXIT_RETRY_FREE,
                ) from e
        yield
    finally:
        if fd is not None:
            os.close(fd)


def reconcile_marker(vendor_dir):
    """The path of a failed rollback's note in vendor_dir, or None."""
    path = os.path.join(vendor_dir, RECONCILE_NAME)
    return path if os.path.lexists(path) else None


def _archive_path(vendor_dir, as_of, now):
    """archive/<as_of>/, or with the time and then a counter added if taken.

    as_of comes from the export's contents, so anything but a plain
    YYYY-MM-DD date is named "undated": a crafted date such as "/tmp/x" or
    "../../x" must not choose where current/ is moved.
    """
    name = as_of if DATE.fullmatch(as_of or "") else "undated"
    base = os.path.join(vendor_dir, "archive", name)
    if not os.path.lexists(base):
        return base
    base += now.strftime("T%H%M%S")
    path, n = base, 1
    while os.path.lexists(path):
        n += 1
        path = f"{base}-{n}"
    return path


def _swap(vendor_dir, staging, old_as_of, now, rebuild):
    """Archive current/, make staging current/, rebuild; undo on failure.

    Returns the archive path, or None when there was no current/.
    """
    current = os.path.join(vendor_dir, "current")
    archive_root = os.path.join(vendor_dir, "archive")
    made_root = not os.path.lexists(archive_root)
    archived = None
    if os.path.lexists(current):
        archived = _archive_path(vendor_dir, old_as_of, now)
        try:
            os.makedirs(archive_root, 0o700, exist_ok=True)
            os.rename(current, archived)
        except OSError as e:
            _remove_if_empty(archive_root, made_root)
            raise StoreError(
                f"can't archive the current export: {e}; nothing changed",
                EXIT_RETRY_FREE,
            ) from e
    step = "install the new export"
    try:
        os.rename(staging, current)
        step = "rebuild"
        if rebuild is not None:
            rebuild()
    except BaseException as e:
        if step == "rebuild":
            _undo(current, staging, archived, e)
        if archived is not None:
            _undo(archived, current, archived, e)
            _remove_if_empty(archive_root, made_root)
        if isinstance(e, Exception):
            state = (
                "the previous export is current again"
                if archived is not None
                else "no export is installed, as before"
            )
            # A rebuild hook's own StoreError keeps its code (the page's
            # exit 4 when no shell is found); anything else is retry-free.
            code = e.code if isinstance(e, StoreError) else EXIT_RETRY_FREE
            raise StoreError(f"couldn't {step} ({e}); {state}", code) from e
        raise
    return archived


def _remove_if_empty(folder, made_it):
    """Remove the archive/ folder this import created, if it is still empty.

    os.rmdir refuses a folder with anything in it, so this can't remove data.
    """
    if made_it:
        with contextlib.suppress(OSError):
            os.rmdir(folder)


def _undo(src, dest, archived, cause):
    try:
        os.rename(src, dest)
    except OSError as e:
        where = f"; the previous export is in {archived}" if archived else ""
        raise StoreError(
            f"import failed ({cause}) and so did undoing it: can't move {src} "
            f"back to {dest} ({e}){where}. Nothing was deleted.",
            EXIT_RECONCILE,
        ) from e


def _detect(vendor, path):
    try:
        return bool(vendor.detect(path))
    except _READ_ERRORS:
        return False


def _claim(path, registry):
    if not os.path.exists(path):
        raise StoreError(f"{path} does not exist", EXIT_UNRECOGNIZED)
    claims = [v for v in registry if _detect(v, path)]
    if not claims:
        known = ", ".join(v.NAME for v in registry)
        raise StoreError(
            f"no store recognizes {path} (known: {known}); nothing changed",
            EXIT_UNRECOGNIZED,
        )
    if len(claims) > 1:
        names = ", ".join(v.NAME for v in claims)
        raise StoreError(
            f"{path} looks like an export of several stores ({names}); "
            "nothing changed",
            EXIT_UNRECOGNIZED,
        )
    return claims[0]


def _stage(vendor, src, staging, current):
    """Install src into staging; read both sides. (old, new, old_as_of, new_as_of)."""
    try:
        vendor.install(src, staging)
    except _READ_ERRORS as e:
        raise StoreError(f"can't unpack {src}: {e}", EXIT_UNRECOGNIZED) from e
    try:
        new = model.finish(vendor.read(staging))
        new_as_of = vendor.as_of(staging)
    except _READ_ERRORS as e:
        raise StoreError(
            f"can't read the export in {src}: {e}", EXIT_UNRECOGNIZED
        ) from e
    if not os.path.isdir(current):
        return [], new, "", new_as_of
    try:
        old = model.finish(vendor.read(current))
        old_as_of = vendor.as_of(current)
    except _READ_ERRORS as e:
        raise StoreError(
            f"can't read the current export {current}: {e}", EXIT_UNRECOGNIZED
        ) from e
    return old, new, old_as_of, new_as_of


def _report(vendor, src, action, old, new, old_as_of, new_as_of):
    report = {
        "store": vendor.ID,
        "name": vendor.NAME,
        "source": src,
        "action": action,
        "as_of": {"old": old_as_of or None, "new": new_as_of or None},
        "archived_to": None,
        "removed_staging": [],
    }
    report.update(compare(vendor, old, new))
    return report


def import_export(data_dir, path, registry, dry_run=False, force=False, **hooks):
    """Import the export at path into data_dir; returns the report.

    The report's "action" is "imported", "dry_run" or "refused_older" (the
    export is older than current/ and force is off: no export was moved,
    though, as with every import but a dry run, leftover staging folders were
    removed). Failures raise StoreError. hooks: rebuild (called after the swap; a
    failure undoes it) and now (a datetime, for archive names).
    """
    rebuild = hooks.get("rebuild")
    now = hooks.get("now") or datetime.datetime.now()
    src = os.path.abspath(path)
    vendor = _claim(src, registry)
    vendor_dir = os.path.join(data_dir, vendor.ID)
    current = os.path.join(vendor_dir, "current")

    if dry_run:
        # Staged outside the data folder, which stays untouched.
        with (
            _shared_lock(data_dir),
            tempfile.TemporaryDirectory(prefix="order-history-") as tmp,
        ):
            staging = os.path.join(tmp, "export")
            os.mkdir(staging, 0o700)
            sides = _stage(vendor, src, staging, current)
            report = _report(vendor, src, "dry_run", *sides)
            report["saved_orders"] = _prune(vendor, vendor_dir, sides[1], True)
        return report

    os.makedirs(vendor_dir, 0o700, exist_ok=True)
    with _lock(data_dir):
        marker = reconcile_marker(vendor_dir)
        if marker:
            raise StoreError(
                f"an earlier {vendor.NAME} import failed and couldn't undo itself; "
                f"see {marker}. Put the folders right, delete that file, then "
                "import again. Nothing changed.",
                EXIT_RECONCILE,
            )
        removed = leftover_staging(vendor_dir)
        for name in removed:
            shutil.rmtree(os.path.join(vendor_dir, name))
        stamp = now.strftime("%Y%m%dT%H%M%S")
        staging = tempfile.mkdtemp(prefix=f"{STAGING_PREFIX}{stamp}-", dir=vendor_dir)
        keep_staging = False
        try:
            old, new, old_as_of, new_as_of = _stage(vendor, src, staging, current)
            older = bool(old_as_of) and new_as_of < old_as_of
            action = "refused_older" if older and not force else "imported"
            report = _report(vendor, src, action, old, new, old_as_of, new_as_of)
            report["removed_staging"] = removed
            report["saved_orders"] = None
            if action == "imported":
                archived = _swap(vendor_dir, staging, old_as_of, now, rebuild)
                if archived is not None:
                    report["archived_to"] = os.path.relpath(archived, data_dir)
                # Only after a successful swap: the new export now holds them.
                report["saved_orders"] = _prune(vendor, vendor_dir, new, False)
        except StoreError as e:
            # After a failed rollback the staging folder may be the only
            # place the new export sits whole: keep it, and stop later imports
            # of this store (which would remove it) until the user has looked.
            if e.code == EXIT_RECONCILE:
                keep_staging = True
                _write_marker(vendor_dir, staging, e)
            raise
        finally:
            if not keep_staging and os.path.isdir(staging):
                # A failure here must not replace the error in flight; status
                # reports the folder and the next import removes it.
                with contextlib.suppress(OSError):
                    shutil.rmtree(staging)
    return report


def _prune(vendor, vendor_dir, new, dry_run):
    """The import report's saved_orders: those the new export replaces.

    None for a vendor without saved orders. A failure here can't undo an
    import that has succeeded, and loses nothing (load() hides saved orders
    the export has), so it is reported as "error" and the next import tries
    again.
    """
    if not saved.supports(vendor):
        return None
    try:
        return saved.prune(vendor_dir, {o["id"] for o in new}, dry_run)
    except (saved.SavedError, OSError) as e:
        return {"replaced_by_export": [], "kept": None, "error": str(e)}


def _write_marker(vendor_dir, staging, error):
    """Write IMPORT-FAILED.txt; if that fails too, say so in the error.

    Without the note the next import would remove the kept staging folder, so
    the message then tells the user not to import until they have looked.
    """
    try:
        with open(os.path.join(vendor_dir, RECONCILE_NAME), "w", encoding="utf-8") as f:
            f.write(
                f"{error}\n\nThe new export, if it isn't in current/, is in "
                f"{staging}.\nWhen current/ holds the export you want, delete "
                "this file.\n"
            )
    except OSError as e:
        raise StoreError(
            f"{error} Writing {RECONCILE_NAME} failed too ({e}): don't run another "
            f"import of this store until the folders are put right; the new "
            f"export is in {staging}.",
            EXIT_RECONCILE,
        ) from error
