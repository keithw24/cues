# Cues

Cues helps a special-education teacher see which students need help. A local camera pipeline watches simple tasks (raise hand, thumbs up, teacher-recorded gestures), a rules engine decides when an event matters, an AI agent suggests support, and the teacher approves every change. The full spec is `PRD-cues.md`.

## Repo layout and owners

| Area | Folder | Owner |
|---|---|---|
| Vision service (camera, MediaPipe, HSEmotion, task events) | `vision/` | Keith |
| Dashboard, station page, Supabase schema | `web/` | Evan |
| Rules engine, Deep Agent, FastAPI backend, Photon | `agent/` | Michelle |
| Shared: CI, this file, feature flags | `.github/`, `CLAUDE.md`, `flags.json`, `.claude/agents/` | everyone |

Only edit another owner's folder when the task needs it, and say so in the PR.

## Commands (vision)

Run from the repo root:

```bash
uv run --project vision pytest                          # unit tests (hardware tests skipped)
CUES_HARDWARE=1 uv run --project vision pytest          # include camera / model tests
uv run --project vision ruff check vision && uv run --project vision ruff format vision
uv run --project vision uvicorn vision.app:app          # service: /stream, /health
uv run --project vision python -m vision.bench          # laptop benchmark
```

`CUES_CAMERA=fake` runs the service without a webcam. Settings are in `vision/.env` (copy `vision/.env.example`).

## Workflow: one feature, one branch, one PR

1. Each feature (one ticket) gets its own branch, `feat/<ticket>-<short-name>`, and its own PR.
2. Base the branch on `main`. If it needs a PR that is not merged yet, base it on that PR's branch and say "Stacked on #N" in the PR body.
3. Fill in the PR template: what it delivers, how it was verified, files owned. List any check CI cannot run (camera, Supabase, Photon) as an unticked box with the exact command.
4. PRs that can be worked on at the same time must not edit the same files.
5. CI (`.github/workflows/`) must pass. Tests that need a camera or model weights use `@pytest.mark.hardware` and are skipped in CI.
6. Every new feature ships behind a feature flag (next section).
7. Before any merge, run the pre-merge review (section after next).

## Feature flags

Every feature can be turned on and off without a code change. This lets the team switch off a feature that misbehaves during the demo, and merge unfinished features safely.

**Registry.** All flags are listed in `flags.json` at the repo root:

```json
"vision.hands": {
  "description": "MediaPipe hand tracking and seat assignment",
  "default": false,
  "owner": "keith",
  "ticket": "T5"
}
```

- Name: `<area>.<feature>`, lower case, where area is `vision`, `web` or `agent`.
- `default` is the value when nothing overrides it.

**Override.** An environment variable overrides the default: the flag name in upper case, dots replaced by underscores, prefixed with `CUES_FLAG_`. Example: `CUES_FLAG_VISION_HANDS=0` turns hand tracking off. The web app reads `NEXT_PUBLIC_CUES_FLAG_...` for flags the browser needs.

**Reading flags.** Each area has one helper and only reads flags through it: `vision/flags.py`, `agent/flags.py`, `web/lib/flags.ts`. Each helper reads `flags.json`, applies the overrides, and treats an unknown flag name as an error.

**Rules for every feature PR:**
1. Add the feature's flag to `flags.json` in the same PR.
2. A new flag starts with `"default": false`. Change it to `true` once the feature has passed its verify step on real hardware; that can be in the same PR if the PR records the hardware check.
3. When the flag is off, the feature's code does not run, and everything else still starts and works. In `vision/`, a stage or router module sets `FLAG = "vision.<feature>"`, and the loader skips the module when the flag is off.
4. Add a test that runs with the flag off and checks that the service still works.
5. Infrastructure that every feature needs (the service skeleton, CI, the flag helper itself) does not get a flag.

## Pre-merge review

Before merging any PR, Claude runs a set of reviewers and reports what they find. Don't merge while a blocking finding is open.

**1. Pick the reviewers from what the PR changes.** Get the changed files with `gh pr diff <N> --name-only`.

| Reviewer (`.claude/agents/`) | When it runs |
|---|---|
| `review-correctness` | always |
| `review-verification` | always |
| `review-flags` | always |
| `review-privacy-contracts` | the PR touches events, `seat_state`, the Supabase schema, expression, the agent, Photon, or anything that sends data off the laptop |

If the PR has a risk no reviewer above covers (for example concurrency, performance on the demo laptop, or a security-sensitive key), create one more reviewer for that risk. Give it a one-paragraph brief, using the same output format as the others.

**2. Run the reviewers in parallel** as subagents. Give each the PR number, the PR's base branch, and the ticket from the vision board or PRD section.

**3. Combine the results** into one list. Remove duplicates and sort it: blocking findings first, then non-blocking ones. Each finding has a file and line, the problem, and a suggested fix.

**4. Post the summary** as a comment on the PR (`gh pr comment <N>`), so the whole team can see it.

**5. Decide.**
- Any blocking finding: don't merge. Fix it on the PR branch, push, and run the affected reviewers again.
- Only non-blocking findings: the PR author decides whether to fix them now or later.
- Merge only after CI passes, no blocking findings are open, and a person on the team has said to merge.

## Product rules every change must respect

These come from the PRD and are not optional:
- Camera frames and images never leave the station laptop. Only structured events go to Supabase, the LLM, or Photon.
- No face recognition. A seat is identified only by its position in the camera frame.
- Expression is supporting evidence only. Never write that Cues detects emotion, distress, or a diagnosis. Expression alone never triggers a "student is struggling" alert.
- The agent picks only from the approved intervention menu. Any change to a student's task needs teacher approval.
- Photon messages contain no images, no expression labels, and no personal details.
- Gesture templates stay on the laptop in `vision/templates/`. Only simulated student data, never real student data.
- The event shape in PRD §17.1 and the tables in §17.3 are shared contracts. Change them only with the agreement of all three owners, and in one PR for all three areas.

## Pushing

If `git push` over SSH is refused, push over HTTPS with the `gh` login:

```bash
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u https://github.com/michelliez/cues.git <branch>
```
