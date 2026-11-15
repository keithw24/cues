"""Local station configuration: the dashboard tells this laptop's vision which station it is.

GET  /config   {"station_id": "S1" | null, "pinned": bool}
POST /config   {"station_id": "S2"}  -> {"station_id": "S2", "changed": true}

The signed-in teacher's dashboard resolves the teacher's station and sends it
here from the browser. Vision does not sign in as the teacher, and no
Supabase key goes to the browser. Only this laptop may configure it:

* the TCP peer must be a loopback address (even if uvicorn binds 0.0.0.0);
* the Host header must be localhost / 127.0.0.1 / [::1] (DNS rebinding);
* the body must be application/json, so a cross-site page cannot send a
  "simple" request without a CORS preflight, and an Origin header, if sent,
  must be one of the dashboard origins (CUES_DASHBOARD_ORIGINS).

Sending the same station again changes nothing (the dashboard re-sends it
every few seconds, so a restarted vision service picks it up again).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from vision import station as station_module

FLAG = "vision.station_config"

LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})

router = APIRouter(tags=["station"])


class StationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station_id: Any  # validated by vision.station.validate for one clear message


def _dashboard_origins() -> set[str]:
    origins = os.environ.get("CUES_DASHBOARD_ORIGINS", "http://localhost:3000")
    return {o.strip() for o in origins.split(",") if o.strip()}


def _host_name(host_header: str) -> str:
    if host_header.startswith("["):  # [::1]:8000
        return host_header.split("]", 1)[0] + "]"
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def require_local(request: Request) -> None:
    peer = request.client.host if request.client else None
    if peer not in LOOPBACK_PEERS:
        raise HTTPException(403, "station configuration is accepted from this laptop only")
    if _host_name(request.headers.get("host", "")) not in LOCAL_HOSTS:
        raise HTTPException(403, "station configuration is accepted on localhost only")
    origin = request.headers.get("origin")
    if origin is not None and origin not in _dashboard_origins():
        raise HTTPException(403, "origin is not the Cues dashboard")


def _state() -> dict:
    from vision.station_lease import STATUS

    current = station_module.STATION
    return {
        "station_id": current.get(),
        "pinned": current.pinned,
        # True while another camera holds this station and this one is paused.
        "station_busy": STATUS.refused,
    }


@router.get("/config", dependencies=[Depends(require_local)])
def read_config() -> dict:
    return _state()


# require_local runs before the body is parsed, so remote callers learn nothing.
@router.post("/config", dependencies=[Depends(require_local)])
def write_config(request: Request, body: StationConfig) -> dict:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "send application/json")
    try:
        changed = station_module.STATION.set(body.station_id, allow_clear=body.station_id is None)
    except station_module.InvalidStationError as exc:
        raise HTTPException(422, str(exc)) from None
    except station_module.StationPinnedError as exc:
        raise HTTPException(409, str(exc)) from None
    return {**_state(), "changed": changed}
