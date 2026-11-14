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
import pkgutil
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

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
    pkg = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package}.{info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)
            log.info("loaded routes %s", info.name)


def create_app(pipeline: Pipeline | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        p = pipeline or Pipeline(camera_from_env(), discover_stages())
        app.state.pipeline = p
        p.start()
        try:
            yield
        finally:
            p.stop()

    app = FastAPI(title="Cues vision", lifespan=lifespan)

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
