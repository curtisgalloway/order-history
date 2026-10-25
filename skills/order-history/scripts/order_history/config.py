# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0

"""Where the data folder is (design R2).

In order of precedence:

  1. --data-dir
  2. $ORDER_HISTORY_DIR
  3. "data_dir" in $XDG_CONFIG_HOME/order-history/config.json
     (~/.config/order-history/config.json when XDG_CONFIG_HOME is unset)
  4. ~/Documents/Order History
"""

import json
import os
import tempfile

ENV_VAR = "ORDER_HISTORY_DIR"
DEFAULT_DIR = os.path.join("~", "Documents", "Order History")


class ConfigError(Exception):
    """The config file exists but can't be used."""


def config_path():
    """The config file's path, honoring XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "order-history", "config.json")


def _read_config():
    path = config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError(f"can't read {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not hold a JSON object")
    return data


def _norm(path):
    return os.path.abspath(os.path.expanduser(path))


def resolve(flag=None):
    """(data folder, where it came from); the folder may not exist yet.

    The source is one of "flag", "env", "config" or "default".
    """
    if flag:
        return _norm(flag), "flag"
    env = os.environ.get(ENV_VAR)
    if env:
        return _norm(env), "env"
    configured = _read_config().get("data_dir")
    if configured:
        return _norm(configured), "config"
    return _norm(DEFAULT_DIR), "default"


def save(data_dir):
    """Record data_dir in the config file, keeping any other keys."""
    path = config_path()
    data = _read_config()  # a broken file is reported, not overwritten
    data["data_dir"] = data_dir
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return path


def init(flag=None):
    """Create the data folder (mode 0700) and record it.

    Returns (data folder, created, config path). An existing folder is kept
    as it is, mode included.
    """
    data_dir, _ = resolve(flag)
    _read_config()  # a broken config file stops init before anything is created
    if os.path.exists(data_dir) and not os.path.isdir(data_dir):
        raise ConfigError(f"{data_dir} exists and is not a folder")
    created = not os.path.isdir(data_dir)
    if created:
        parent = os.path.dirname(data_dir)
        os.makedirs(parent, exist_ok=True)
        os.mkdir(data_dir, 0o700)
        # mkdir's mode is filtered by the umask; set it outright.
        os.chmod(data_dir, 0o700)
    return data_dir, created, save(data_dir)
