"""Model files and loaders shared by the benchmark and the pipeline stages.

MediaPipe Tasks needs model files on disk. They are downloaded once from
Google's model storage into vision/models/ (git-ignored). HSEmotion downloads
and caches its own ONNX weights on first use.
"""

from __future__ import annotations

import logging
import shutil
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"
DOWNLOAD_TIMEOUT = 30  # seconds; a stalled network fails instead of hanging the service

MODEL_URLS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
    "gesture_recognizer.task": (
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
        "gesture_recognizer/float16/1/gesture_recognizer.task"
    ),
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
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
    try:
        with urllib.request.urlopen(MODEL_URLS[name], timeout=DOWNLOAD_TIMEOUT) as resp:
            with open(tmp, "wb") as out:
                shutil.copyfileobj(resp, out)
    except Exception:
        tmp.unlink(missing_ok=True)  # never leave a half-downloaded model behind
        raise
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


def gesture_recognizer(num_hands: int = 4):
    """MediaPipe Gesture Recognizer in IMAGE mode.

    Returns the same 21 hand landmarks and handedness as the Hand Landmarker,
    plus a score per hand for each built-in gesture: Thumb_Up, Thumb_Down,
    Open_Palm, Closed_Fist, Pointing_Up, Victory, ILoveYou and None. Trained on
    many people and angles, so it handles viewpoint changes far better than
    matching recorded examples.
    """
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.components.processors import ClassifierOptions
    from mediapipe.tasks.python.vision import GestureRecognizer, GestureRecognizerOptions

    options = GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("gesture_recognizer.task"))),
        num_hands=num_hands,
        canned_gesture_classifier_options=ClassifierOptions(max_results=-1, score_threshold=0.0),
    )
    return GestureRecognizer.create_from_options(options)


def pose_landmarker(num_poses: int = 4, video: bool = True):
    """MediaPipe Pose Landmarker (lite): 33 body points per person.

    video=True uses VIDEO mode: MediaPipe follows each person from one frame to
    the next instead of searching from scratch, so poses flicker much less.
    Call detect_for_video(image, timestamp_ms) with increasing timestamps.
    """
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path("pose_landmarker_lite.task"))),
        running_mode=RunningMode.VIDEO if video else RunningMode.IMAGE,
        num_poses=num_poses,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return PoseLandmarker.create_from_options(options)


def expression_recognizer():
    """HSEmotion ONNX recognizer (8 classes), running on CPU."""
    from hsemotion_onnx.facial_emotions import HSEmotionRecognizer

    return HSEmotionRecognizer(model_name=HSEMOTION_MODEL)
