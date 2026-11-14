"""Gesture examples over HTTP, for the dashboard's gesture-recording controls.

POST   /templates/record        records examples from the running service
GET    /templates/{activity_id} how many examples are stored
DELETE /templates/{activity_id} deletes all examples for that activity

Recording reads hands from the live pipeline (the same hands the gesture stage
uses), so the service keeps running and keeps the camera. Examples are saved
only on this laptop in vision/templates/.

Example:
    curl -X POST localhost:8000/templates/record -H 'Content-Type: application/json' \
         -d '{"activity_id": "custom_gesture_01", "label": "target", "seat_id": "S1-P1"}'
"""

from __future__ import annotations

import time

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from vision import activities
from vision.gestures import templates as tpl
from vision.gestures.matcher import calibrate_rejection
from vision.gestures.normalize import normalize

FLAG = "vision.gestures"
SAMPLE_HZ = 10.0

router = APIRouter(prefix="/templates", tags=["templates"])


class RecordRequest(BaseModel):
    activity_id: str
    label: str = Field(pattern="^(target|rest)$")
    seconds: float = Field(default=2.0, gt=0, le=10)
    seat_id: str | None = None  # a seat or person id; None = the largest hand in view


def pick_hand(hands_by_seat: dict, seat_id: str | None):
    hands = (
        hands_by_seat.get(seat_id, [])
        if seat_id
        else [h for hs in hands_by_seat.values() for h in hs]
    )
    if not hands:
        return None
    return max(hands, key=lambda h: float(np.ptp(h.landmarks[:, :2], axis=0).prod()))


def collect(ctx: dict, seconds: float, seat_id: str | None, sample_hz: float = SAMPLE_HZ):
    """Sample the live ctx["hands"] for `seconds`. Returns hand vectors."""
    vectors = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        hand = pick_hand(ctx.get("hands", {}), seat_id)
        if hand is not None:
            vectors.append(normalize(hand.landmarks, hand.handedness))
        time.sleep(1.0 / sample_hz)
    return vectors


def summary(templates: tpl.Templates) -> dict:
    target, rest = templates.arrays()
    return {
        "activity_id": templates.activity_id,
        "target_examples": len(target),
        "rest_examples": len(rest),
        "rejection_threshold": round(calibrate_rejection(target, rest), 3) if len(target) else None,
    }


def gesture_activity(activity_id: str):
    try:
        activity = activities.get(activity_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if activity.check_type != "gesture":
        raise HTTPException(status_code=422, detail=f"{activity_id} is not a gesture task")
    return activity


@router.post("/record")
def record(body: RecordRequest, request: Request) -> dict:
    activity = gesture_activity(body.activity_id)
    vectors = collect(request.app.state.pipeline.ctx, body.seconds, body.seat_id)
    if not vectors:
        raise HTTPException(status_code=422, detail="no hand seen; nothing recorded")
    templates = tpl.load(activity.id)
    if templates.stale:  # recorded with older code: start again
        templates = tpl.Templates(activity.id)
    templates.add(body.label, vectors)
    tpl.save(templates)
    return {"captured": len(vectors), **summary(templates)}


@router.get("/{activity_id}")
def get_templates(activity_id: str) -> dict:
    return summary(tpl.load(gesture_activity(activity_id).id))


@router.delete("/{activity_id}")
def delete_templates(activity_id: str) -> dict:
    return {"deleted": tpl.delete(gesture_activity(activity_id).id)}
