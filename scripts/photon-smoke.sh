#!/usr/bin/env bash
# One harmless send to the configured session owner's Supabase profile phone.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m agent.photon_smoke
