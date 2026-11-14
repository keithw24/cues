import os
import subprocess
from pathlib import Path


def test_demo_forces_dynamic_and_dev_preserves_override(tmp_path):
    root = Path(__file__).resolve().parents[2]
    # Replace only the shared launch target in isolated copies of the wrappers.
    helper = tmp_path / "run-stack.sh"
    helper.write_text('#!/bin/sh\nprintf "%s" "$CUES_USE_STATIC_TEACHER_PHONE"\n')
    helper.chmod(0o755)
    for name, expected in [("demo.sh", "0"), ("dev.sh", "1")]:
        wrapper = tmp_path / name
        wrapper.write_text((root / "scripts" / name).read_text())
        result = subprocess.run(
            ["bash", str(wrapper)],
            env={**os.environ, "CUES_USE_STATIC_TEACHER_PHONE": "1"},
            text=True,
            capture_output=True,
            check=True,
        )
        assert result.stdout == expected
