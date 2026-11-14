"""Teacher-recorded gesture examples, stored only on this laptop.

Each activity has one file, vision/templates/<activity_id>.json:

    {"activity_id": "thumbs_up",
     "target": [[63 numbers], ...],   # examples of the gesture
     "rest":   [[63 numbers], ...]}   # examples of other / relaxed hands

vision/templates/ is git-ignored (except the built-in thumbs_up.json), so
examples are never synced or committed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
LABELS = ("target", "rest")


@dataclass
class Templates:
    activity_id: str
    target: list[list[float]] = field(default_factory=list)
    rest: list[list[float]] = field(default_factory=list)

    def add(self, label: str, vectors: list[np.ndarray]) -> None:
        if label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}")
        getattr(self, label).extend([list(map(float, v)) for v in vectors])

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return (
            np.array(self.target, dtype=np.float64).reshape(-1, 63),
            np.array(self.rest, dtype=np.float64).reshape(-1, 63),
        )


def path_for(activity_id: str, directory: Path | None = None) -> Path:
    directory = TEMPLATES_DIR if directory is None else directory
    if not activity_id.replace("_", "").isalnum():
        raise ValueError(f"invalid activity id {activity_id!r}")
    return directory / f"{activity_id}.json"


def load(activity_id: str, directory: Path | None = None) -> Templates:
    path = path_for(activity_id, directory)
    if not path.exists():
        return Templates(activity_id)
    data = json.loads(path.read_text())
    return Templates(activity_id, data.get("target", []), data.get("rest", []))


def save(templates: Templates, directory: Path | None = None) -> Path:
    directory = TEMPLATES_DIR if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(templates.activity_id, directory)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {
                "activity_id": templates.activity_id,
                "target": templates.target,
                "rest": templates.rest,
            }
        )
    )
    tmp.replace(path)
    return path


def delete(activity_id: str, directory: Path | None = None) -> bool:
    path = path_for(activity_id, directory)
    if path.exists():
        path.unlink()
        return True
    return False
