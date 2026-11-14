"""Local process supervisor with component logs and group cleanup."""

import argparse
import os
import signal
import subprocess
import threading
import time

from dotenv import load_dotenv

from shared.supabase_client import REPO_ROOT


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
    required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GROQ_API_KEY", "CUES_SESSION_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Configure root .env: " + ", ".join(required))
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
