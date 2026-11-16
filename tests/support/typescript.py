"""Run the dashboard's real TypeScript parsers from Python tests."""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/contract/ts_consumer.ts"


def run_parser(kind: str, data, station: str = "") -> dict:
    """Feed `data` to the TypeScript parser `kind`; raises AssertionError with its message."""
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
