"""Teacher-created gestures over HTTP, for the dashboard's "add a gesture" flow.

GET    /gestures              every gesture task, with how many examples each has
POST   /gestures              create a new recorded gesture: {"name": "Wave"}
DELETE /gestures/{id}         remove a gesture created here, and its examples

Flow for the dashboard:
  1. POST /gestures {"name": "Wave"}           -> {"id": "custom_wave", ...}
  2. POST /templates/record {"activity_id": "custom_wave", "label": "target"}  x3
  3. POST /templates/record {..., "label": "rest"}                           x2
  4. GET  /gestures -> "ready": true. The gesture is detected live right away.

The gesture definition and its examples stay in vision/templates/ on this laptop.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vision import activities
from vision.gestures import templates as tpl

router = APIRouter(prefix="/gestures", tags=["gestures"])


class CreateGesture(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    keywords: list[str] = Field(default_factory=list, max_length=10)


def describe(activity) -> dict:
    out = {
        "id": activity.id,
        "name": activity.name,
        "builtin": activity.builtin is not None,
        "custom": activities.is_custom(activity.id),
        "success_threshold": activity.success_threshold,
        "review_threshold": activity.review_threshold,
    }
    if activity.builtin:
        out.update(target_examples=None, rest_examples=None, ready=True)
    else:
        t = tpl.load(activity.id)
        target, rest = (0, 0) if t.stale else (len(t.target), len(t.rest))
        out.update(target_examples=target, rest_examples=rest, ready=target > 0)
    return out


@router.get("")
def list_gestures() -> list[dict]:
    return [describe(a) for a in activities.load_activities().values() if a.check_type == "gesture"]


@router.post("", status_code=201)
def create_gesture(body: CreateGesture) -> dict:
    try:
        activity = activities.add_custom_gesture(body.name, tuple(body.keywords))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return describe(activity)


@router.delete("/{activity_id}")
def delete_gesture(activity_id: str) -> dict:
    if not activities.is_custom(activity_id):
        raise HTTPException(
            status_code=404, detail=f"{activity_id} was not created from the dashboard"
        )
    activities.remove_custom_gesture(activity_id)
    tpl.delete(activity_id)
    return {"deleted": True}
