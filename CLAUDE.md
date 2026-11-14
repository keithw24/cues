# Cues

Cues helps a special-education teacher see which students need help. A local camera pipeline watches simple tasks (raise hand, thumbs up, teacher-recorded gestures), a rules engine decides when an event matters, an AI agent suggests support, and the teacher approves every change. The full spec is `PRD-cues.md`.

## Repo layout and owners

| Area | Folder | Owner |
|---|---|---|
| Vision service (camera, MediaPipe, HSEmotion, task events) | `vision/` | Keith |
| Dashboard, station page, Supabase schema | `web/` | Evan |
| Rules engine, Deep Agent, FastAPI backend, Photon | `agent/` | Michelle |
| Shared: CI, this file, team workflow, feature flags | `.github/`, `CLAUDE.md`, `TEAM_WORKFLOW.md`, `flags.json`, `.claude/agents/` | everyone |

Only edit another owner's folder when the task needs it, and say so in the PR.

## Environment

One shared Python environment for the whole repo, set up by Michelle: `pyproject.toml` and `uv.lock` at the root, Python 3.11 (`.python-version`). Run `uv sync` once. Add Python dependencies only to the root `pyproject.toml` with `uv add`; don't create per-folder Python projects. Secrets go in the root `.env`; copy `.env.example`. The vision service reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from it. Optional vision settings, also in `.env` or the shell: `CUES_CAMERA_INDEX` (webcam number, default 0), `CUES_CAMERA=fake`, `CUES_STATION_ID` (default `S1`) and `CUES_SESSION_ID` (default: a new id on each start). The web app has its own `web/package.json`.

## Commands (vision)

Run from the repo root.

Checks (the same ones CI runs):

```bash
uv run pytest vision                   # unit tests (hardware tests skipped)
CUES_HARDWARE=1 uv run pytest vision   # include camera / model tests
uv run ruff check vision
uv run ruff format --check vision
```

Fix formatting (rewrites files): `uv run ruff format vision`

Run the service and tools:

```bash
uv run uvicorn vision.app:app          # service: /stream, /health
uv run python -m vision.bench          # laptop benchmark
uv run python -m vision.events --demo  # send one test event
```

## Workflow and naming

`TEAM_WORKFLOW.md` is the source of truth for how the team works. In short:

**Branches.** Each person works on their own branch, named after them. `main` is for integration only; nobody commits to it directly.

| Branch | Who | Area |
|---|---|---|
| `keith` | Keith | `vision/` |
| `evan` | Evan | `web/`, Supabase |
| `michelle` | Michelle | `agent/` |
| `main` | everyone | integration |

Don't create other branches (no `feat/...`, no per-ticket branches) unless the team agrees.

**Before starting work**, bring in the latest `main`:

```bash
git switch <your-name>
git pull
git merge main
```

**Commits.** Small and scoped to one change. The message is a short imperative description of what changed, for example `Add hand tracking stage` or `Fix seat dead band`. No ticket prefixes. Push regularly. Don't force-push unless the whole team agrees.

**Merging into `main`.** Open a pull request from your branch into `main`.
- **Title:** short and plain, a few words naming what it adds, for example `Hand tracking`, `Gesture matching`, `Cleanup`. No ticket numbers, prefixes or person names.
- **Body:** fill in the PR template. List any check CI cannot run (camera, Supabase, Photon) as an unticked box with the exact command and who will run it.
- **Before opening it:** merge the latest `main` into your branch and resolve conflicts there, not on `main`.
- **Before merging it:** CI passes and the pre-merge review (below) has no open blocking finding.

**Feature flag names** follow the pattern in the next section (`<area>.<feature>`, for example `vision.hands`).

**Checks.** CI (`.github/workflows/`) must pass. Tests that need a camera or model weights use `@pytest.mark.hardware` and are skipped in CI. CI only runs for paths that have a workflow, so "No checks reported" is fine for a PR that changes none of those paths. Don't make the `vision` check a required status check: PRs that skip it would wait on it forever.

**Shared files.** Stay in your own area. `flags.json` is shared: add only your own entries. If you must change another person's files for integration, say so in the PR.

## Feature flags

Every feature can be turned on and off without a code change. This lets the team switch off a feature that misbehaves during the demo, and merge unfinished features safely.

**Registry.** All flags are listed in `flags.json` at the repo root. Example entry (T5 will add this one):

```json
"vision.hands": {
  "description": "MediaPipe hand tracking and seat assignment",
  "default": false,
  "owner": "keith",
  "ticket": "T5"
}
```

- Name: `<area>.<feature>`, matching `^(vision|web|agent)\.[a-z0-9_]+$`.
- Every entry has `description` (text), `default` (true or false), `owner` and `ticket`. A test in `vision/tests/` checks this.

**Override.** An environment variable overrides the default: the flag name in upper case, with dots replaced by underscores, prefixed with `CUES_FLAG_`. Example: `CUES_FLAG_VISION_HANDS=0` turns hand tracking off.
- `1` or `true` means on; `0` or `false` means off; any other value is an error.
- The web app reads `NEXT_PUBLIC_CUES_FLAG_...` for flags the browser needs. If both forms are set, `CUES_FLAG_...` wins on the server.

**Reading flags.** Each area has one helper and only reads flags through it: `vision/flags.py`, `agent/flags.py`, `web/lib/flags.ts`. Each helper reads `flags.json`, applies the overrides, and treats an unknown flag name as an error.

**Status:** `vision/flags.py` exists. The vision stage and route loaders skip modules whose `FLAG` is off, and `/health` lists every vision flag's current value. `agent/flags.py` and `web/lib/flags.ts` are not built yet; until an area's helper exists, don't merge a flagged feature in that area into `main`.

**Rules for every feature:**
1. Add the feature's flag to `flags.json` in the same change as the feature.
2. A new flag starts with `"default": false`. Change it to `true` once the feature's Verify step has passed (on real hardware, if the feature needs a camera or model). That can happen in the same PR into `main` if the PR records the check.
3. When the flag is off, the feature's code does not run, and everything else still starts and works. Two patterns:
   - **A whole module** (a stage or router in `vision/`): the module sets `FLAG = "vision.<feature>"`, and the loader skips it when the flag is off.
   - **A behaviour inside code that always runs** (for example, sending events to Supabase instead of only to local files): check the flag where the choice is made. The flag-off path is the fallback.
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
| `review-privacy-contracts` | the PR touches any of: events, `seat_state` or the Supabase schema; expression; the agent; Photon; voice; gesture templates; logs, frame or image writes; `.gitignore`; the "Product rules" section of this file; or anything that sends data off the laptop |

If the PR has a risk none of these reviewers covers (for example concurrency, performance on the demo laptop, or a security-sensitive key), add one more reviewer for that risk:
- run it as a one-off general-purpose subagent with a one-paragraph brief;
- give it the same output format as the others;
- don't add a file for it.

**2. Run the reviewers in parallel** as subagents. Give each one the PR number and the PR's base branch; it reads the ticket and Verify step from the PR body. If the `review-*` agent types are not available in the session (they load only when a session starts), spawn a general-purpose subagent for each one, telling it to read its `.claude/agents/review-*.md` file and follow it.

**3. Combine the results** into one list. Remove duplicates and sort it: blocking findings first, then non-blocking ones. Each finding has a file and line, the problem, and a suggested fix.

**4. Post the summary** as a comment on the PR (`gh pr comment <N>`), so the whole team can see it.

**5. Decide.**
- Any blocking finding: don't merge. The PR author's session fixes it on the PR branch and pushes; then the affected reviewers run again. A session reviewing someone else's PR only reports.
- Only non-blocking findings: the PR author decides whether to fix them now or later.
- Merge only after CI passes, no blocking findings are open, and a person on the team has said to merge.

## Product rules every change must respect

These come from the PRD and are not optional.

**Privacy**
- Camera frames, images and raw camera data never leave the station laptop. Only structured events go to Supabase, the LLM, or Photon. The privacy claim is "student camera images and video stay local". Don't claim that all audio stays on-device (teacher voice may use a hosted speech service).
- No face recognition or other biometric identification. A seat is identified only by its position in the camera frame.
- Gesture templates stay on the laptop in `vision/templates/` and are git-ignored. One exception: `vision/templates/thumbs_up.json` is the built-in thumbs-up, recorded by a developer, and contains no student data.
- Only simulated student data during the hackathon, never real student data.
- No secrets in git, and no secrets in browser-visible variables (`NEXT_PUBLIC_*`).

**Expression and inference**
- Expression is supporting evidence only. Expression alone never triggers a "student is struggling" alert.
- Never claim that Cues detects emotion, distress, intent, attention, or a diagnosis. Use "facial-expression context", "expression signal" and "model probability".
- The live expression distribution is not stored as history. Only meaningful `expression_context` events are stored.
- No behavioural scoring and no grading of students.

**Agent and teacher approval**
- The agent never sees camera frames, never diagnoses, and never claims anything about a child's internal state.
- The agent picks only from the approved intervention menu.
- Teacher approval is needed before Cues changes a student's task, an instruction, or a support intervention. A teacher notification does not need approval.
- If the LLM call fails or times out, the agent falls back to a deterministic, rule-based alert.

**Photon**
- Messages contain the minimum necessary information only: no images or raw camera data, no expression labels, no diagnoses, no unnecessary personal details.

**Shared contracts**
- The event shape in PRD §17.1 and the tables in §17.3 are shared by all three areas. A change to them updates `vision/`, `web/`, `agent/` and PRD §17 in one PR, and the PR body records sign-off from Keith, Evan and Michelle.

## Pushing

If `git push` over SSH is refused, push over HTTPS with the `gh` login:

```bash
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u https://github.com/michelliez/cues.git <branch>
```
