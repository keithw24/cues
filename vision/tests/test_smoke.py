import vision


def test_package_imports():
    assert vision.__version__


def test_core_dependencies_import():
    import cv2
    import fastapi
    import mediapipe
    import numpy

    assert cv2 and fastapi and mediapipe and numpy
