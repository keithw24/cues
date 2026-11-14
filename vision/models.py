"""Model files and loaders shared by the benchmark and the pipeline stages.

MediaPipe Tasks needs model files on disk. They are downloaded once from
Google's model storage into vision/models/ (git-ignored). HSEmotion downloads
and caches its own ONNX weights on first use.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"

MODEL_URLS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
    "blaze_face_short_range.tflite": (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    ),
}

HSEMOTION_MODEL = "enet_b0_8_best_vgaf"


def model_path(name: str, models_dir: Path = MODELS_DIR) -> Path:
    """Return the local path of a MediaPipe model, downloading it if missing."""
    if name not in MODEL_URLS:
        raise KeyError(f"unknown model {name!r}; known: {sorted(MODEL_URLS)}")
    path = models_dir / name
    if path.exists() and path.stat().st_size > 0:
        return path
    models_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    log.info("downloading %s", name)
    urllib.request.urlretrieve(MODEL_URLS[name], tmp)
    tmp.rename(path)
    return path


def hand_landmarker(num_hands: int = 4):
    """MediaPipe Hand Landmarker in IMAGE mode (one call per frame)."""
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("hand_landmarker.task"))),
        num_hands=num_hands,
    )
    return HandLandmarker.create_from_options(options)


def face_detector(min_confidence: float = 0.5):
    """MediaPipe short-range face detector in IMAGE mode."""
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions

    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("blaze_face_short_range.tflite"))),
        min_detection_confidence=min_confidence,
    )
    return FaceDetector.create_from_options(options)


def expression_recognizer():
    """HSEmotion ONNX recognizer (8 classes), running on CPU."""
    from hsemotion_onnx.facial_emotions import HSEmotionRecognizer

    return HSEmotionRecognizer(model_name=HSEMOTION_MODEL)
