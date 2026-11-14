"""The grouping the running service uses: one id per tracked person.

Stages import GROUPING from here. It is a vision.people.PeopleGrouping with
ids(), hand_owner(), face_owner(), anchor() and color().
"""

from __future__ import annotations

from vision.people import grouping_from_env

GROUPING = grouping_from_env()
