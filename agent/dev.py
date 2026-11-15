"""Local process supervisor with component logs and group cleanup."""

import argparse
import os
import signal
import socket
import subprocess
import threading
import time

from dotenv import load_dotenv

from shared.supabase_client import REPO_ROOT


def clear_cues_port(port, grace_seconds=5):
    """Reclaim a stale Cues listener, never an unidentified or unrelated server."""
    result = subprocess.run(
        ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    for value in set(result.stdout.split()):
        pid = int(value)
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
        ).stdout.strip()
        cwd = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        directories = [line[1:] for line in cwd if line.startswith("n")]
        expected = REPO_ROOT / "web" if port == 3000 else REPO_ROOT
        known_command = (
            ("next-server" in command or "next dev" in command)
            if port == 3000
            else "uvicorn" in command and "vision.app:app" in command
        )
        if str(expected) not in directories or not known_command:
            raise SystemExit(
                f"Port {port} belongs to another/unidentified process; leaving it running."
            )
        print(f"Stopping previous Cues server on port {port} (PID {pid}).", flush=True)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            remaining = subprocess.run(
                ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
            ).stdout.split()
            if str(pid) not in remaining:
                break
            time.sleep(0.1)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def port_is_free(port: int) -> bool:
    """True when nothing is listening on the port.

    A plain bind() also fails while a server that just stopped has connections still
    draining (TIME_WAIT: up to a minute on macOS, for example a browser tab left on the
    dashboard video), although nothing is listening and the real servers start fine. So ask
    who is listening instead. If lsof is unavailable, fall back to the strict bind test.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                return False
            return True
    return not result.stdout.split()


def cleanup(children, grace_seconds=5):
    """Terminate only isolated groups started by this supervisor; safe to repeat."""
    groups = {child.pid for child in children}

    def signal_group(group, sig):
        try:
            os.killpg(group, sig)
            return True
        except ProcessLookupError:
            return False

    for group in groups:
        signal_group(group, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while groups and time.monotonic() < deadline:
        # Reap direct children, but keep checking their groups independently.
        for child in children:
            child.poll()
        groups = {group for group in groups if signal_group(group, 0)}
        if groups:
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    for group in groups:
        signal_group(group, signal.SIGKILL)
    for child in children:
        child.wait()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("dev", "demo"), default="dev")
    profile = parser.parse_args().profile
    load_dotenv(REPO_ROOT / ".env")
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Configure root .env: " + ", ".join(required))
    for port in (3000, 8000):
        clear_cues_port(port)
        if not port_is_free(port):
            raise SystemExit(
                f"Port {port} is already in use. Stop the existing Cues "
                "server before running ./scripts/dev.sh or ./scripts/demo.sh."
            )
    commands = [
        (
            "vision",
            ["uv", "run", "uvicorn", "vision.app:app", "--host", "127.0.0.1", "--port", "8000"],
            REPO_ROOT,
        ),
        ("agent", ["uv", "run", "python", "-m", "agent.worker", "--profile", profile], REPO_ROOT),
        ("web", ["npm", "run", "dev", "--", "--port", "3000"], REPO_ROOT / "web"),
    ]
    children = []
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    def output(name, stream):
        for line in stream:
            print(f"[{name}] {line}", end="", flush=True)

    vision_env = os.environ.copy()
    for stage in (
        "HANDS",
        "FACES",
        "GESTURES",
        "RAISE_HAND",
        "EXPRESSION",
        "TASK_STATUS",
        "SUPABASE_EVENTS",
        "ACTIVITY_SYNC",
        "SESSION_LIFECYCLE",
    ):
        key = f"CUES_FLAG_VISION_{stage}"
        if not vision_env.get(key):
            vision_env[key] = "1"
    print(
        f"Mode: {profile.upper()}\nAgent timing: {profile}\n"
        f"Camera index: {vision_env.get('CUES_CAMERA_INDEX', '0')}\n"
        "Dashboard: http://localhost:3000\n"
        "Vision health: http://127.0.0.1:8000/health",
        flush=True,
    )
    print(
        "Vision: "
        + " ".join(
            key.removeprefix("CUES_FLAG_VISION_").lower() + "=" + value
            for key, value in vision_env.items()
            if key.startswith("CUES_FLAG_VISION_") and value in ("0", "1", "true", "false")
        ),
        flush=True,
    )

    try:
        for name, command, cwd in commands:
            child = subprocess.Popen(
                command,
                cwd=cwd,
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=vision_env if name == "vision" else os.environ.copy(),
            )
            children.append(child)
            threading.Thread(target=output, args=(name, child.stdout), daemon=True).start()
        while not stop.wait(0.2):
            if any(child.poll() is not None for child in children):
                raise SystemExit("A component exited; stopping stack")
    finally:
        cleanup(children)


if __name__ == "__main__":
    main()
