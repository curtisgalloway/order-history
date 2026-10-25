# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""What the vendors' enrich() functions share (design R6).

`order-history update` calls enrich(vendor_dir, opts, orders) on every vendor
that has one, with orders read from current/ under the import lock. The
network call, the clock and the jitter all come from Options, so tests replace
them and no test reaches a store.

enrich() returns a result from new_result():

  store     the vendor ID
  skipped   why nothing was attempted (e.g. Amazon without --amazon-images)
  requests  HTTP requests made
  changed   cache entries written
  pending   lookups still missing after this run
  failed    [{"id", "error"}] for lookups that failed without stopping the run
  stopped   None, or {"reason", "message"} when the run stopped early; reason
            is "throttled" (429/5xx or a captcha), "unreachable" (a network
            error or other 5xx on an Amazon product page), "robots"
            (robots.txt disallows the page) or "robots_unreadable"
  error     a precondition that stopped this vendor (e.g. no lookup email)
"""

import dataclasses
import datetime
import http.client
import json
import os
import random
import sys
import tempfile
import time
import typing
import urllib.error
import urllib.request


class EnrichError(Exception):
    """A vendor can't run its enrichment at all; `code` is the exit code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def http_read(req, timeout):
    """The response body for req; raises OSError (HTTPError for a status)."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        e.close()  # it holds the response open; callers need only e.code
        raise
    except http.client.HTTPException as e:  # e.g. IncompleteRead: not an OSError
        raise OSError(f"{type(e).__name__}: {e}") from e


def _log(msg):
    print(msg, file=sys.stderr)


@dataclasses.dataclass
class Options:
    """What enrich() may use. Tests pass urlopen, sleep, uniform and random."""

    email: str = ""  # --email; the vendor falls back to its own sources
    amazon_images: bool = False
    dry_run: bool = False
    # urlopen(request, timeout) -> bytes
    urlopen: typing.Optional[typing.Callable] = None
    sleep: typing.Optional[typing.Callable] = None
    uniform: typing.Optional[typing.Callable] = None  # random.uniform(a, b)
    random: typing.Optional[typing.Callable] = None  # random.random()
    log: typing.Optional[typing.Callable] = None
    today: typing.Optional[datetime.date] = None

    def __post_init__(self):
        self.urlopen = self.urlopen or http_read
        self.sleep = self.sleep or time.sleep
        self.uniform = self.uniform or random.uniform
        self.random = self.random or random.random
        self.log = self.log or _log
        self.today = self.today or datetime.date.today()


def new_result(store):
    """An empty enrich() result for the vendor `store`."""
    return {
        "store": store,
        "skipped": None,
        "requests": 0,
        "changed": 0,
        "pending": 0,
        "failed": [],
        "stopped": None,
        "error": None,
    }


def write_json(path, data, **dump_args):
    """Write data as JSON to path through a temporary file (mode 0600)."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + "-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_args)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
