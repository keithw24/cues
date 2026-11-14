"""Local process supervisor with component logs and group cleanup."""

import os
import signal
import subprocess
import threading

from dotenv import load_dotenv

from shared.supabase_client import REPO_ROOT


def main():
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
        ("agent", ["uv", "run", "python", "-m", "agent.worker"], REPO_ROOT),
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
    for stage in ("HANDS", "FACES", "GESTURES", "RAISE_HAND", "EXPRESSION", "TASK_STATUS"):
        vision_env[f"CUES_FLAG_VISION_{stage}"] = "1"

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
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == "__main__":
    main()
