import argparse

import pytest

from vision import bench, models


def test_summarize_reports_mean_p95_and_fps():
    t = bench.summarize("x", [10.0] * 18 + [50.0] * 2)
    assert t.runs == 20
    assert t.mean_ms == pytest.approx(14.0)
    assert t.p95_ms == 50.0
    assert t.solo_fps == pytest.approx(1000 / 14)


def test_summarize_empty():
    assert bench.summarize("x", []).runs == 0


def test_schedule_fps_fills_one_second_budget():
    # faces 10 ms x 5 Hz = 50 ms; expression 20 ms x 3 Hz x 2 seats = 120 ms
    # remaining 830 ms / 20 ms per hands frame = 41.5 fps, capped at 30
    assert bench.schedule_fps(20, 10, 20, base_fps=30) == 30
    assert bench.schedule_fps(83, 10, 20, base_fps=30) == pytest.approx(10.0)


def test_schedule_fps_zero_when_fixed_work_exceeds_budget():
    assert bench.schedule_fps(10, 100, 200, base_fps=30) == 0.0


def test_model_path_uses_existing_file_without_download(tmp_path):
    existing = tmp_path / "hand_landmarker.task"
    existing.write_bytes(b"model")
    assert models.model_path("hand_landmarker.task", models_dir=tmp_path) == existing


def test_model_path_rejects_unknown_model(tmp_path):
    with pytest.raises(KeyError):
        models.model_path("nope.task", models_dir=tmp_path)


@pytest.mark.hardware
def test_bench_runs_end_to_end_on_synthetic_frames():
    """Downloads the models, so it only runs with CUES_HARDWARE=1."""
    args = argparse.Namespace(seconds=3, camera=0, video=None, fake=True, json=False)
    report = bench.run(args)
    assert report["frames"] > 0
    assert all(t["runs"] > 0 for t in report["timings"])
