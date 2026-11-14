"""Cues vision service (FastAPI).

Run from the repo root:

    uv run uvicorn vision.app:app --port 8000

Then open http://localhost:8000/stream for the live video and
http://localhost:8000/health for the camera status and frame rates.
Set CUES_CAMERA=fake to run without a webcam.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from vision import flags
from vision.camera import camera_from_env
from vision.pipeline import Pipeline, discover_stages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("vision")

BOUNDARY = "frame"


def mjpeg_parts(pipeline: Pipeline, max_frames: int | None = None) -> Iterator[bytes]:
    """Yield multipart MJPEG chunks, one per new pipeline frame."""
    index = 0
    sent = 0
    while max_frames is None or sent < max_frames:
        index, jpeg = pipeline.wait_for_jpeg(after=index, timeout=1.0)
        if jpeg is None:
            continue
        yield (
            f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
            f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
            + jpeg
            + b"\r\n"
        )
        sent += 1


def include_routes(app: FastAPI, package: str = "vision.routes") -> None:
    """Include every module's `router`, skipping modules whose FLAG is off."""
    pkg = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package}.{info.name}")
        router = getattr(module, "router", None)
        flag = getattr(module, "FLAG", None)
        if router is not None and flag is not None and not flags.enabled(flag):
            log.info("skipped routes %s (flag %s is off)", info.name, flag)
            continue
        if router is not None:
            app.include_router(router)
            log.info("loaded routes %s", info.name)


def create_app(pipeline: Pipeline | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from vision.activity_sync import sync_from_env

        p = pipeline or Pipeline(camera_from_env(), discover_stages())
        app.state.pipeline = p
        sync = sync_from_env() if pipeline is None else None
        p.start()
        if sync is not None:
            sync.start()
        try:
            yield
        finally:
            if sync is not None:
                sync.stop()
            p.stop()

    app = FastAPI(title="Cues vision", lifespan=lifespan)
    # Let the local dashboard call the gesture APIs from the browser. Only the
    # dashboard's own origin(s); the service still listens on this laptop only.
    from fastapi.middleware.cors import CORSMiddleware

    origins = os.environ.get("CUES_DASHBOARD_ORIGINS", "http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health(request: Request) -> dict:
        return request.app.state.pipeline.health()

    @app.get("/stream")
    def stream(request: Request) -> StreamingResponse:
        return StreamingResponse(
            mjpeg_parts(request.app.state.pipeline),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        )

    include_routes(app)
    return app


app = create_app()
