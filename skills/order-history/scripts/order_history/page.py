# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""The search page: a page shell plus the order data (design R7).

The page shell is the page built once by Vite (web/) with its
<script id="order-data"> element left empty. build() puts the order data in
that element and writes <data>/index.html. Node is needed only to build a
shell, never to fill one. A shell for this version comes from, in order:

  1. the cache, $XDG_CACHE_HOME/order-history/page-shell-<version>.html
     (~/.cache/... when XDG_CACHE_HOME is unset);
  2. a local build, when this package sits in a checkout that has web/ and
     npm is on PATH (development); not cached, so edits to web/ show up;
  3. a download of page-shell.html from the GitHub release tagged
     v<version>, which is then cached.

When none of them works, build() raises PageError (exit 4) and leaves the
existing page alone.
"""

import datetime
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from order_history import __version__, model

EXIT_NO_SHELL = 4

# The data format the page understands; web/src/load.ts has the same number.
# Bump both together when the data's shape changes.
FORMAT = 1

PLACEHOLDER = '<script id="order-data" type="application/json"></script>'
_OPEN = '<script id="order-data" type="application/json">'
RELEASE_URL = (
    "https://github.com/curtisgalloway/order-history/releases/download/"
    "v{version}/page-shell.html"
)
SHELL_NAME = "page-shell-{version}.html"
PAGE_NAME = "index.html"
# A shell is about 300 kB; anything far larger is not one.
MAX_SHELL_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT = 60
# npm ci on a first install can be slow, but must not hang an import forever.
NPM_TIMEOUT = 600

# The repository root when this package runs from a checkout:
# <root>/skills/order-history/scripts/order_history/page.py
_CHECKOUT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)
WEB_DIR = os.path.join(_CHECKOUT, "web")


class PageError(Exception):
    """No page shell could be found, or the page couldn't be written."""

    def __init__(self, message, code=EXIT_NO_SHELL):
        super().__init__(message)
        self.code = code


def _log(msg):
    print(msg, file=sys.stderr)


def cache_dir():
    """Where downloaded shells are kept, honoring XDG_CACHE_HOME."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return os.path.join(base, "order-history")


def release_url(version=__version__):
    """The URL of this version's page shell on its GitHub release."""
    return RELEASE_URL.format(version=version)


def is_shell(text):
    """True when text is a page shell: one empty order-data element."""
    return text.count(_OPEN) == 1 and text.count(PLACEHOLDER) == 1


def _write_atomic(path, text, mode=0o600):
    """Write text to path through a temporary file renamed into place."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + "-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


# ---- finding a shell ------------------------------------------------------


def _from_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as e:
        return None, f"cached shell {path} can't be read ({e})"
    if not is_shell(text):
        return None, f"cached shell {path} is not a page shell"
    return text, None


def build_shell(web_dir=WEB_DIR):
    """Build the shell with npm in web_dir; returns its text.

    Raises OSError or subprocess.CalledProcessError on failure. npm's output
    is captured, so stdout stays clean for --json.
    """
    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("npm is not on PATH")
    _log(f"building the page shell with npm in {web_dir}")
    if not os.path.isdir(os.path.join(web_dir, "node_modules")):
        _npm(npm, "ci", cwd=web_dir)
    _npm(npm, "run", "build", cwd=web_dir)
    with open(os.path.join(web_dir, "dist", "index.html"), encoding="utf-8") as f:
        return f.read()


def _npm(npm, *args, cwd):
    subprocess.run(
        [npm, *args], cwd=cwd, check=True, capture_output=True, timeout=NPM_TIMEOUT
    )


def _can_build_locally(web_dir):
    return os.path.isfile(os.path.join(web_dir, "package.json")) and bool(
        shutil.which("npm")
    )


def download(url):
    """The text at url (the release asset); raises OSError or ValueError."""
    req = urllib.request.Request(
        url, headers={"User-Agent": f"order-history/{__version__}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            body = resp.read(MAX_SHELL_BYTES + 1)
    except http.client.HTTPException as e:  # e.g. IncompleteRead: not an OSError
        raise OSError(f"{type(e).__name__}: {e}") from e
    if len(body) > MAX_SHELL_BYTES:
        raise ValueError(f"more than {MAX_SHELL_BYTES} bytes")
    return body.decode("utf-8")


def _describe(e):
    if isinstance(e, subprocess.CalledProcessError):
        tail = (e.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
        cmd = " ".join(e.cmd[1:])
        return f"`{cmd}` exited {e.returncode}" + (
            ": " + " / ".join(tail) if tail else ""
        )
    return str(e) or type(e).__name__


def find_shell(**hooks):
    """(shell text, where it came from: "cache", "local build" or "download").

    hooks, for tests: version, cache (a folder), web_dir, build (web_dir ->
    text) and fetch (url -> text). Raises PageError when no source works.
    """
    version = hooks.get("version") or __version__
    cache = hooks.get("cache") or cache_dir()
    web_dir = hooks.get("web_dir") or WEB_DIR
    builder = hooks.get("build") or build_shell
    fetch = hooks.get("fetch") or download
    cached = os.path.join(cache, SHELL_NAME.format(version=version))
    reasons = []

    text, problem = _from_cache(cached)
    if text is not None:
        return text, "cache"
    if problem:
        reasons.append(problem)

    if _can_build_locally(web_dir):
        try:
            text = builder(web_dir)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            reasons.append(f"local build failed ({_describe(e)})")
        else:
            if is_shell(text):
                return text, "local build"
            reasons.append("the local build is not a page shell")

    url = release_url(version)
    try:
        text = fetch(url)
    except (OSError, ValueError) as e:  # urllib.error.URLError is an OSError
        reasons.append(f"download failed ({_describe(e)})")
    else:
        if is_shell(text):
            try:
                os.makedirs(cache, exist_ok=True)
                _write_atomic(cached, text, mode=0o644)
            except OSError as e:
                _log(f"order-history: couldn't cache the page shell: {e}")
            return text, "download"
        reasons.append("the download is not a page shell")

    raise PageError(
        f"no page shell for version {version}: " + "; ".join(reasons) + ". "
        f"It is published at {url}; connect to the network, or build it from a "
        "checkout with Node installed. The existing page is unchanged."
    )


# ---- filling it -----------------------------------------------------------


def page_data(loaded, today=None):
    """The data the page reads: format, generated, stores, orders.

    loaded is [(vendor, orders or None)] as the CLI loads it; vendors with no
    export are left out.
    """
    stores, orders = [], []
    for vendor, vendor_orders in loaded:
        if vendor_orders is None:
            continue
        stores.append(
            {
                "id": vendor.ID,
                "name": vendor.NAME,
                "source": getattr(vendor, "SOURCE", vendor.NAME + " export"),
            }
        )
        orders += vendor_orders
    model.finish(orders)
    return {
        "format": FORMAT,
        "generated": (today or datetime.date.today()).isoformat(),
        "stores": stores,
        "orders": [model.compact(o) for o in orders],
    }


def to_script_text(data):
    """data as JSON that is safe inside a <script> element.

    Every "<" is written as \\u003c, so no "</script", "<!--" or "<script" in
    the data can end the element or change how the browser parses it; the
    JSON means the same thing.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c")


def fill(shell, data):
    """The page: shell with data in its order-data element."""
    if not is_shell(shell):
        raise PageError("the page shell has no empty order-data element")
    return shell.replace(PLACEHOLDER, _OPEN + to_script_text(data) + "</script>", 1)


def build(data_dir, loaded, **hooks):
    """Write <data_dir>/index.html; returns {"path", "shell", "orders"}.

    Raises PageError (exit 4) when no shell can be found; the existing page
    is then left as it was. hooks: as find_shell(), plus today (a date).
    """
    shell, source = find_shell(**hooks)
    data = page_data(loaded, hooks.get("today"))
    page = fill(shell, data)
    path = os.path.join(data_dir, PAGE_NAME)
    try:
        _write_atomic(path, page)
    except OSError as e:
        raise PageError(f"can't write {path}: {e}") from e
    return {"path": path, "shell": source, "orders": len(data["orders"])}
