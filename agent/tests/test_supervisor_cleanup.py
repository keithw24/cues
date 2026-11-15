import os
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent import dev
from agent.dev import cleanup


@pytest.mark.parametrize("owned", [True, False])
def test_port_recovery_only_stops_verified_cues_server(monkeypatch, owned):
    outputs = iter(
        [
            "123\n",
            "next-server (v16)\n",
            "p123\nn" + str(dev.REPO_ROOT / "web" if owned else "/tmp/another-project") + "\n",
            "",
        ]
    )
    monkeypatch.setattr(
        dev.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=next(outputs))
    )
    kill = MagicMock()
    monkeypatch.setattr(dev.os, "kill", kill)
    if owned:
        dev.clear_cues_port(3000)
        kill.assert_called_once_with(123, signal.SIGTERM)
    else:
        with pytest.raises(SystemExit, match="leaving it running"):
            dev.clear_cues_port(3000)
        kill.assert_not_called()


def test_surviving_descendant_is_killed_after_parent_exits(tmp_path):
    ready = tmp_path / "ready"
    # The direct child exits on TERM; its descendant deliberately ignores TERM.
    code = """
import os, signal, sys, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open(sys.argv[1], 'w') as f: f.write(str(os.getpid()))
    while True: time.sleep(1)
while True: time.sleep(1)
"""
    parent = subprocess.Popen([sys.executable, "-c", code, str(ready)], start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        descendant = int(ready.read_text())
        cleanup([parent], grace_seconds=0.1)
        assert parent.returncode is not None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(descendant)], capture_output=True, text=True
            ).stdout.strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(0.01)
        assert not state or state.startswith("Z")
        cleanup([parent], grace_seconds=0)
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.wait()


def test_leftovers_need_a_known_command_and_this_repos_folder():
    web, root = str(dev.REPO_ROOT / "web"), str(dev.REPO_ROOT)
    rows = [
        (10, "node /x/next/dist/bin/next dev --port 3000"),  # this repo's dashboard
        (11, "node /x/next/dist/bin/next dev --port 3001"),  # another project's
        (12, "python -m agent.worker --profile demo"),  # this repo's worker
        (13, "python -m agent.worker --profile demo"),  # a copy in another folder
        (14, "vim notes.md"),  # not ours at all
        (15, "uvicorn vision.app:app --port 8000"),  # this repo's vision
        (16, "python -m agent.worker"),  # own process: never swept
    ]
    folders = {10: web, 11: "/other/web", 12: root, 13: "/other", 14: root, 15: root, 16: root}
    found = dev.find_leftovers(rows, folders.get, own={16})
    assert [pid for pid, _ in found] == [10, 12, 15]


def test_sweep_stops_leftovers_with_term_then_kill(monkeypatch):
    monkeypatch.setattr(dev, "_process_table", lambda: [(40, "python -m agent.worker")])
    monkeypatch.setattr(dev, "_working_directory", lambda pid: str(dev.REPO_ROOT))
    monkeypatch.setattr(dev, "_own_pids", lambda: set())
    sent = []
    monkeypatch.setattr(dev.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    monkeypatch.setattr(dev, "_is_alive", lambda pid: True)  # ignores TERM
    assert dev.sweep_leftovers(grace_seconds=0) == [40]
    assert sent == [(40, signal.SIGTERM), (40, signal.SIGKILL)]


def test_sweep_does_nothing_when_nothing_is_left(monkeypatch):
    monkeypatch.setattr(dev, "_process_table", lambda: [(1, "launchd")])
    monkeypatch.setattr(dev, "_own_pids", lambda: set())
    kill = MagicMock()
    monkeypatch.setattr(dev.os, "kill", kill)
    assert dev.sweep_leftovers(grace_seconds=0) == []
    kill.assert_not_called()


def test_closing_the_terminal_stops_the_stack_cleanly(monkeypatch):
    import threading

    handlers = {}
    monkeypatch.setattr(dev.signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    stop = threading.Event()
    dev.install_stop_signals(stop)
    assert {signal.SIGINT, signal.SIGTERM, signal.SIGHUP} <= set(handlers)
    handlers[signal.SIGHUP](signal.SIGHUP, None)
    assert stop.is_set()
