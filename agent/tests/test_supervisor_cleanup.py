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
