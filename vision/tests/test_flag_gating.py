"""Modules with a FLAG are skipped by the stage and route loaders when it is off."""

import importlib
import sys
import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vision import flags
from vision.app import include_routes
from vision.pipeline import discover_stages

REGISTRY = {
    "vision.gate_on": {"description": "x", "default": True, "owner": "k", "ticket": "T0"},
    "vision.gate_off": {"description": "x", "default": False, "owner": "k", "ticket": "T0"},
}

STAGE = """
{flag_line}
class _S:
    name = "{name}"
    rate_hz = None
    def process(self, frame, ctx): pass
    def draw(self, image, ctx): pass

def create_stage():
    return _S()
"""

ROUTE = """
from fastapi import APIRouter
{flag_line}
router = APIRouter()

@router.get("/{name}")
def handler():
    return {{"ok": True}}
"""


def make_package(root, package, template):
    pkg_dir = root / package
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    modules = [("a_noflag", None), ("b_on", "vision.gate_on"), ("c_off", "vision.gate_off")]
    for name, flag in modules:
        flag_line = f'FLAG = "{flag}"' if flag else ""
        body = template.format(flag_line=flag_line, name=name)
        (pkg_dir / f"{name}.py").write_text(textwrap.dedent(body))


@pytest.fixture
def gated(tmp_path, monkeypatch):
    monkeypatch.setattr(flags, "load_registry", lambda: REGISTRY)
    monkeypatch.syspath_prepend(str(tmp_path))
    for env in ("CUES_FLAG_VISION_GATE_ON", "CUES_FLAG_VISION_GATE_OFF"):
        monkeypatch.delenv(env, raising=False)
    yield tmp_path
    for mod in [m for m in sys.modules if m.startswith(("gstages", "groutes"))]:
        del sys.modules[mod]
    importlib.invalidate_caches()


def test_stage_with_flag_off_is_skipped(gated):
    make_package(gated, "gstages", STAGE)
    names = [s.name for s in discover_stages("gstages")]
    assert names == ["a_noflag", "b_on"]


def test_env_override_turns_stage_on_and_off(gated, monkeypatch):
    make_package(gated, "gstages", STAGE)
    monkeypatch.setenv("CUES_FLAG_VISION_GATE_OFF", "1")
    monkeypatch.setenv("CUES_FLAG_VISION_GATE_ON", "0")
    names = [s.name for s in discover_stages("gstages")]
    assert names == ["a_noflag", "c_off"]


def test_route_with_flag_off_is_skipped(gated):
    make_package(gated, "groutes", ROUTE)
    app = FastAPI()
    include_routes(app, "groutes")
    client = TestClient(app)
    assert client.get("/a_noflag").status_code == 200
    assert client.get("/b_on").status_code == 200
    assert client.get("/c_off").status_code == 404
