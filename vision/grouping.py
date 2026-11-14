"""The grouping the running service uses: people (default) or fixed seats.

Stages import GROUPING from here. It is either a vision.people.PeopleGrouping
(CUES_GROUPING=people, the default) or the fixed left/right vision.seats.ZONES
(CUES_GROUPING=seats). Both have the same methods: ids(), hand_owner(),
face_owner(), anchor() and color().
"""

from __future__ import annotations

from vision.people import grouping_from_env

GROUPING = grouping_from_env()
