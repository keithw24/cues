"""Seat zones: which seat a detection belongs to.

One camera watches two seats. A vertical divider splits the frame into a left
seat and a right seat. A detection is assigned by the x position of its
centre (in normalised image coordinates, 0 = left edge, 1 = right edge).

Detections within `dead_band` of the divider are ignored, so a hand reaching
across the middle is not credited to the wrong child. `swap()` flips which
seat id is on which side, for when the children sit the other way round.

No face recognition: a seat is identified only by position.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field


@dataclass
class SeatZones:
    station_id: str = "S1"
    divider: float = 0.5
    dead_band: float = 0.05
    swapped: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def left_id(self) -> str:
        return f"{self.station_id}-{'R' if self.swapped else 'L'}"

    @property
    def right_id(self) -> str:
        return f"{self.station_id}-{'L' if self.swapped else 'R'}"

    @property
    def seat_ids(self) -> list[str]:
        return [f"{self.station_id}-L", f"{self.station_id}-R"]

    def assign(self, x: float) -> str | None:
        """Seat id for a normalised x, or None inside the dead band or off-frame."""
        with self._lock:
            if not 0.0 <= x <= 1.0:
                return None
            if abs(x - self.divider) < self.dead_band:
                return None
            return self.left_id if x < self.divider else self.right_id

    def set_divider(self, x: float) -> None:
        if not 0.1 <= x <= 0.9:
            raise ValueError("divider must be between 0.1 and 0.9")
        with self._lock:
            self.divider = x

    def swap(self) -> None:
        with self._lock:
            self.swapped = not self.swapped

    def as_dict(self) -> dict:
        return {
            "station_id": self.station_id,
            "divider": self.divider,
            "dead_band": self.dead_band,
            "left": self.left_id,
            "right": self.right_id,
        }


def zones_from_env() -> SeatZones:
    return SeatZones(
        station_id=os.environ.get("CUES_STATION_ID", "S1"),
        divider=float(os.environ.get("CUES_SEAT_DIVIDER", "0.5")),
    )


# The one set of zones the running service uses. Stages read it; routes change it.
ZONES = zones_from_env()
