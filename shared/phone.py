"""The one definition of a valid destination phone number (E.164, e.g. +12025550101)."""

import re

E164 = re.compile(r"\+[1-9][0-9]{7,14}")


def is_e164(value: object) -> bool:
    return isinstance(value, str) and E164.fullmatch(value) is not None
