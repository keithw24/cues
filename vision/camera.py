"""Camera capture.

The vision service is the only process that opens the webcam. A background
thread reads frames continuously and keeps only the newest one, so slow
consumers never build up a backlog.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480


@dataclass
class Frame:
    image: np.ndarray  # BGR, as OpenCV returns it
    timestamp: float  # time.monotonic() when captured
    index: int  # increases by 1 for every captured frame


class Camera:
    """Base class: start(), stop(), latest(), is_open."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Frame | None = None
        self._count = 0
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def is_open(self) -> bool:
        return self._running

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def start(self) -> None:
        if self._running:
            return
        self._open()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._close()

    def _publish(self, image: np.ndarray) -> None:
        with self._lock:
            self._count += 1
            self._latest = Frame(image=image, timestamp=time.monotonic(), index=self._count)

    # Subclasses implement these.
    def _open(self) -> None: ...
    def _close(self) -> None: ...
    def _loop(self) -> None: ...


class OpenCVCamera(Camera):
    """A real webcam read through OpenCV."""

    def __init__(
        self, index: int = 0, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT
    ) -> None:
        super().__init__()
        self.index = index
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None

    def _open(self) -> None:
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open camera {self.index}. Check it is connected and that this "
                "terminal has camera permission (System Settings > Privacy > Camera)."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap

    def _close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _loop(self) -> None:
        while self._running and self._cap is not None:
            ok, image = self._cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            if image.shape[1] != self.width or image.shape[0] != self.height:
                image = cv2.resize(image, (self.width, self.height))
            self._publish(image)


class FakeCamera(Camera):
    """Synthetic frames for tests and for running without a webcam.

    Draws a moving bar so the stream visibly updates.
    """

    def __init__(
        self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, fps: float = 30.0
    ) -> None:
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps

    def _loop(self) -> None:
        period = 1.0 / self.fps
        while self._running:
            image = np.full((self.height, self.width, 3), 40, dtype=np.uint8)
            x = (self._count * 8) % self.width
            cv2.rectangle(image, (x, 0), (x + 20, self.height), (200, 200, 200), -1)
            self._publish(image)
            time.sleep(period)


def camera_from_env() -> Camera:
    """CUES_CAMERA=fake for synthetic frames; otherwise CUES_CAMERA_INDEX (default 0)."""
    if os.environ.get("CUES_CAMERA", "").lower() == "fake":
        return FakeCamera()
    return OpenCVCamera(index=int(os.environ.get("CUES_CAMERA_INDEX", "0")))
