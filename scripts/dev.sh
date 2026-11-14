#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for tool in uv node npm; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
exec uv run python -m agent.dev
