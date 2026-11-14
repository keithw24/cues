"""Seat controls: swap the two seats, move the divider. Infrastructure: no flag."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vision.seats import ZONES

router = APIRouter(prefix="/seats", tags=["seats"])


class Divider(BaseModel):
    x: float


@router.get("")
def get_seats() -> dict:
    return ZONES.as_dict()


@router.post("/swap")
def swap() -> dict:
    ZONES.swap()
    return ZONES.as_dict()


@router.post("/divider")
def set_divider(body: Divider) -> dict:
    try:
        ZONES.set_divider(body.x)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ZONES.as_dict()
