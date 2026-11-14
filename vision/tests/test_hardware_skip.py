"""The hardware-skip hook in conftest.py skips only tests with the real marker."""

from pathlib import Path

CONFTEST = (Path(__file__).parent / "conftest.py").read_text()

TESTS = """
import pytest

@pytest.mark.hardware
def test_marked():
    pass

def test_plain():
    pass
"""


def _setup(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    hardware: needs hardware\n")


def test_marked_test_skipped_by_default(pytester, monkeypatch):
    monkeypatch.delenv("CUES_HARDWARE", raising=False)
    _setup(pytester)
    pytester.makepyfile(TESTS)
    pytester.runpytest().assert_outcomes(passed=1, skipped=1)


def test_marked_test_runs_with_cues_hardware(pytester, monkeypatch):
    monkeypatch.setenv("CUES_HARDWARE", "1")
    _setup(pytester)
    pytester.makepyfile(TESTS)
    pytester.runpytest().assert_outcomes(passed=2)


def test_folder_named_hardware_is_not_skipped(pytester, monkeypatch):
    monkeypatch.delenv("CUES_HARDWARE", raising=False)
    _setup(pytester)
    pytester.mkpydir("hardware")
    pytester.path.joinpath("hardware", "test_plain_in_folder.py").write_text(
        "def test_plain():\n    pass\n"
    )
    pytester.runpytest().assert_outcomes(passed=1)
