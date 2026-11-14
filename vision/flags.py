"""Feature flags for the vision service.

Every feature can be turned on or off without a code change (see "Feature
flags" in CLAUDE.md).

* The registry is `flags.json` at the repo root. Each entry has a `default`.
* An environment variable overrides the default: `CUES_FLAG_` + the flag name
  in upper case with dots replaced by underscores. Example:
  `CUES_FLAG_VISION_SUPABASE_EVENTS=1`.
* `1` or `true` means on, `0` or `false` means off (any case). Any other value
  is an error, so a typo never silently picks a state.
* Asking for a flag that is not in `flags.json` is an error.

Usage:

    from vision import flags

    if flags.enabled("vision.supabase_events"):
        ...
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

FLAGS_FILE = Path(__file__).resolve().parent.parent / "flags.json"

TRUE_VALUES = frozenset({"1", "true"})
FALSE_VALUES = frozenset({"0", "false"})


class UnknownFlagError(KeyError):
    """The flag name is not in flags.json."""


class InvalidFlagValueError(ValueError):
    """The CUES_FLAG_* environment variable is not 1/true/0/false."""


@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict[str, Any]]:
    return json.loads(FLAGS_FILE.read_text())


def env_name(flag: str) -> str:
    return "CUES_FLAG_" + flag.upper().replace(".", "_")


def enabled(flag: str, env: Mapping[str, str] | None = None) -> bool:
    """True if the flag is on: the env override if set, else the registry default."""
    registry = load_registry()
    if flag not in registry:
        raise UnknownFlagError(f"{flag!r} is not in flags.json; add it there first")
    env = os.environ if env is None else env
    raw = env.get(env_name(flag))
    if raw is None or raw == "":
        return bool(registry[flag]["default"])
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise InvalidFlagValueError(f"{env_name(flag)}={raw!r}: use 1, true, 0 or false")


def snapshot(env: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Current value of every vision flag, for /health and logs."""
    return {
        name: enabled(name, env) for name in sorted(load_registry()) if name.startswith("vision.")
    }
