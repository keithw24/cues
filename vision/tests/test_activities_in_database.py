"""The activities a teacher can pick (database) must match what vision can detect."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_builtin_gesture_is_seeded_with_vision_values():
    catalog = json.loads((ROOT / "vision/activities.json").read_text())
    builtins = [a for a in catalog if a.get("builtin")]
    assert builtins, "expected built-in gestures in the vision catalog"
    sql = (ROOT / "supabase/migrations/20261114001400_builtin_gestures.sql").read_text()
    seed = (ROOT / "supabase/seed.sql").read_text()
    for activity in builtins:
        row = re.search(
            rf"\('{activity['id']}', '{re.escape(activity['name'])}', '{activity['check_type']}', "
            rf"array\[(.*?)\], ([0-9.]+), ([0-9.]+), (\d+),",
            sql,
        )
        assert row, f"{activity['id']} is missing from the built-in gestures migration"
        assert [k.strip("' ") for k in row.group(1).split(",")] == activity["keywords"]
        assert float(row.group(2)) == activity["success_threshold"]
        assert float(row.group(3)) == activity["review_threshold"]
        assert int(row.group(4)) == activity["no_progress_seconds"]
        assert f"('{activity['id']}'," in seed  # fresh databases get it too
