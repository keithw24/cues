#!/usr/bin/env bash
set -euo pipefail
export CUES_USE_STATIC_TEACHER_PHONE=0
exec "$(dirname "$0")/run-stack.sh" demo
