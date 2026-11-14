"""Frame pipeline.

The pipeline takes the newest camera frame, runs each stage that is due, draws
every stage's overlay onto a copy of the frame, and keeps the result as a JPEG
for the /stream endpoint.

Stages plug in by adding a module to `vision/stages/` that defines
`create_stage() -> Stage`. No shared file needs editing, so stages built in
parallel never touch the same file.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
import time
from collections import deque
from typing import Any, Protocol

import cv2
import numpy as np

from vision.camera import Camera, Frame

log = logging.getLogger(__name__)


class Stage(Protocol):
    name: str
    # Maximum runs per second. None means every frame.
    rate_hz: float | None

    def process(self, frame: Frame, ctx: dict[str, Any]) -> None:
        """Read the frame and write results into ctx (shared by all stages)."""

    def draw(self, image: np.ndarray, ctx: dict[str, Any]) -> None:
        """Draw this stage's overlay onto image (a copy of the frame) in place."""


class RateMeter:
    """Counts events and reports events per second over the last few seconds."""

    def __init__(self, window_s: float = 2.0) -> None:
        self.window_s = window_s
        self._times: deque[float] = deque()

    def tick(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._times.append(now)
        self._trim(now)

    def rate(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._trim(now)
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0

    def _trim(self, now: float) -> None:
        while self._times and now - self._times[0] > self.window_s:
            self._times.popleft()


def discover_stages(package: str = "vision.stages") -> list[Stage]:
    """Import every module in the package and collect create_stage() results.

    Modules are loaded in name order, so a stage that reads another stage's
    ctx output should sort after it (e.g. s20_faces after s10_hands) or simply
    tolerate missing keys.
    """
    pkg = importlib.import_module(package)
    stages: list[Stage] = []
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{package}.{info.name}")
        factory = getattr(module, "create_stage", None)
        if factory is None:
            continue
        stages.append(factory())
        log.info("loaded stage %s", info.name)
    return stages


class Pipeline:
    def __init__(self, camera: Camera, stages: list[Stage], jpeg_quality: int = 80) -> None:
        self.camera = camera
        self.stages = stages
        self.jpeg_quality = jpeg_quality
        self.ctx: dict[str, Any] = {}
        self.loop_rate = RateMeter()
        self.stage_rates = {s.name: RateMeter() for s in stages}
        self._last_run: dict[str, float] = {}
        self._jpeg: bytes | None = None
        self._jpeg_index = 0
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self.camera.start()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.camera.stop()

    # ---- processing ------------------------------------------------------
    def step(self, frame: Frame) -> bytes:
        """Run due stages on one frame and return the annotated JPEG."""
        now = time.monotonic()
        for stage in self.stages:
            if self._due(stage, now):
                try:
                    stage.process(frame, self.ctx)
                except Exception:
                    log.exception("stage %s failed", stage.name)
                self._last_run[stage.name] = now
                self.stage_rates[stage.name].tick(now)

        image = frame.image.copy()
        for stage in self.stages:
            try:
                stage.draw(image, self.ctx)
            except Exception:
                log.exception("stage %s draw failed", stage.name)

        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        self.loop_rate.tick(now)
        return buf.tobytes()

    def _due(self, stage: Stage, now: float) -> bool:
        if stage.rate_hz is None:
            return True
        last = self._last_run.get(stage.name)
        return last is None or now - last >= 1.0 / stage.rate_hz

    def _loop(self) -> None:
        last_index = 0
        while self._running:
            frame = self.camera.latest()
            if frame is None or frame.index == last_index:
                time.sleep(0.005)
                continue
            last_index = frame.index
            jpeg = self.step(frame)
            with self._cond:
                self._jpeg = jpeg
                self._jpeg_index += 1
                self._cond.notify_all()

    # ---- outputs ---------------------------------------------------------
    def wait_for_jpeg(self, after: int, timeout: float = 1.0) -> tuple[int, bytes | None]:
        """Block until a JPEG newer than `after` exists. Returns (index, jpeg)."""
        with self._cond:
            self._cond.wait_for(lambda: self._jpeg_index > after, timeout=timeout)
            return self._jpeg_index, self._jpeg

    def health(self) -> dict[str, Any]:
        return {
            "camera_open": self.camera.is_open,
            "fps": round(self.loop_rate.rate(), 1),
            "stages": {name: round(m.rate(), 1) for name, m in self.stage_rates.items()},
        }
