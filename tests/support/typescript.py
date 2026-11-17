"""Run the dashboard's real TypeScript code from Python tests."""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/contract/ts_consumer.ts"


def run_parser(kind: str, data, station: str = "") -> dict:
    """Feed `data` to the dashboard code `kind` (see ts_consumer.ts) and return what it made of it.

    Raises AssertionError with the TypeScript error when the dashboard rejects the data.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(data, handle)
    try:
        result = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                "--no-warnings",
                str(RUNNER),
                kind,
                handle.name,
                station,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
        )
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if result.returncode:
        raise AssertionError(
            f"TypeScript parser {kind!r} rejected the data:\n{result.stderr[-600:]}"
        )
    return json.loads(result.stdout.strip().splitlines()[-1])
