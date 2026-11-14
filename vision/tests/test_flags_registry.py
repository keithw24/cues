"""flags.json (repo root) follows the registry rules in CLAUDE.md."""

import json
import re
from pathlib import Path

FLAGS_FILE = Path(__file__).resolve().parents[2] / "flags.json"
NAME = re.compile(r"^(vision|web|agent)\.[a-z0-9_]+$")
REQUIRED = {"description": str, "default": bool, "owner": str, "ticket": str}


def load():
    return json.loads(FLAGS_FILE.read_text())


def test_flags_file_is_an_object():
    assert isinstance(load(), dict)


def test_flag_names_follow_the_pattern():
    bad = [name for name in load() if not NAME.match(name)]
    assert not bad, f"flag names must match {NAME.pattern}: {bad}"


def test_every_flag_has_required_fields_with_right_types():
    for name, entry in load().items():
        for field, kind in REQUIRED.items():
            assert field in entry, f"{name} is missing {field!r}"
            assert isinstance(entry[field], kind), f"{name}.{field} must be {kind.__name__}"
            if kind is str:
                assert entry[field].strip(), f"{name}.{field} is empty"
