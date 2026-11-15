# Cues

Cues helps a special-education teacher see which students need help. A local camera pipeline watches simple tasks (raise hand, thumbs up, teacher-recorded gestures), a rules engine decides when an event matters, an AI agent suggests support, and the teacher approves every change. The full spec is `notes/PRD-cues.md`.

## Repo layout and owners

| Area | Folder | Owner |
|---|---|---|
| Vision service (camera, MediaPipe, HSEmotion, task events) | `vision/` | Keith |
| Frontend, app backend, station page, Supabase schema | `web/` dashboard and Supabase product integration | Evan |
| Agent / routing, rules engine, Deep Agent, LLM integration, Photon | `agent/` | Michelle |
| Shared: CI, this file, feature flags | `.github/`, `CLAUDE.md`, `flags.json`, `.claude/agents/` | everyone |

Only edit another owner's folder when the task needs it, and say so in the PR.

## Environment

One shared Python environment for the whole repo, set up by Michelle: `pyproject.toml` and `uv.lock` at the root, Python 3.11 (`.python-version`). Run `uv sync` once. Add Python dependencies only to the root `pyproject.toml` with `uv add`; don't create per-folder Python projects. Secrets go in the root `.env`; copy `.env.example`. The vision service reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from it. Optional vision settings, also in `.env` or the shell: `CUES_CAMERA_INDEX` (webcam number, default 0), `CUES_CAMERA=fake`, `CUES_STATION_ID` (dev/test override only: normally the signed-in teacher's dashboard sends the station to `POST 127.0.0.1:8000/config`; with the override set, vision refuses any other station) and `CUES_SESSION_ID` (legacy/smoke commands only: with the session lifecycle on, which the launcher does by default, vision follows the station's active session from Supabase). The web app has its own `web/package.json`.

## Commands (vision)

Run from the repo root.

Checks. CI runs three workflows, each only when its own paths change:

| Workflow | Runs when | What it runs |
|---|---|---|
| `vision` | `vision/`, `shared/`, `agent/`, `flags.json`, `pyproject.toml`, `uv.lock` | `ruff check` and `ruff format --check` on `vision shared agent`, then `pytest vision shared/tests agent/tests` |
| `web` | `web/`, `cues/`, `flags.json` | in `web/`: `npm ci`, `npx next typegen`, `npx tsc --noEmit`, `npm run lint`, `npm test`, `npm run build` |
| `supabase` | `supabase/`, `pyproject.toml`, `uv.lock` | `ruff` on `supabase`, then `pytest supabase` against a real PostgreSQL (replays every migration). A skipped database test fails the step |

The same checks locally, from the repo root:

```bash
uv run pytest vision shared/tests agent/tests   # unit tests (hardware tests skipped)
CUES_HARDWARE=1 uv run pytest vision            # include camera / model tests
uv run ruff check vision shared agent
uv run ruff format --check vision shared agent
(cd web && npx next typegen && npx tsc --noEmit && npm run lint && npm test && npm run build)
# Database tests need PostgreSQL's initdb, pg_ctl and psql on the PATH. On a Mac with Homebrew:
PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH" LC_ALL=en_US.UTF-8 uv run pytest supabase
```

Fix formatting (rewrites files): `uv run ruff format vision`

Run the service and tools:

```bash
uv run uvicorn vision.app:app          # service: /stream, /health, /config, /gestures, /templates
uv run python -m vision.bench          # laptop benchmark
uv run python -m vision.events --demo  # send one test event
```


## Workflow: personal branches and scoped PRs

`notes/archive/TEAM_WORKFLOW.md` defines the current branches and ownership: `keith` for CV, `evan` for frontend/app backend, `michelle` for agent/routing, and `main` for integration.

1. Work on your personal branch and keep each change scoped to one task.
2. Follow `notes/archive/TEAM_WORKFLOW.md` for synchronizing with `main` and resolving conflicts on your branch before integration.
3. Fill in the PR template:
   - the ticket ID, and its Verify step copied word for word (the ticket list is not in the repo, so the PR body is where reviewers read it);
   - what it delivers, and how it was verified;
   - the feature flag, if any;
   - the files owned.
   List any check CI cannot run (camera, Supabase, Photon) as an unticked box with the exact command and the name of the person who will run it.
4. PRs that are worked on at the same time must not edit the same files. One exception: `flags.json` is shared. Each PR only adds its own entry and rebases if another PR's entry conflicts.
5. CI (`.github/workflows/`) must pass. Tests that need a camera or model weights use `@pytest.mark.hardware` and are skipped in CI. CI only runs for paths that have a workflow (`vision`, `web`, `supabase`). "No checks reported" is fine for a PR that changes none of those paths (for example notes or docs only). Don't make the `vision`, `web` or `supabase` check a required status check: PRs that skip it would wait on it forever.
6. Every new feature ships behind a feature flag (next section).
7. Before any merge, run the pre-merge review (section after next).

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

**Status:** `vision/flags.py` exists. The vision stage and route loaders skip modules whose `FLAG` is off, and `/health` lists every vision flag's current value. `web/lib/flags.ts` exists too. `agent/flags.py` is not built yet: the agent worker reads its flag (`agent.live_progress`) through `vision/flags.py`. Until `agent/flags.py` exists, an agent feature either reuses that helper or ships with a flag-off fallback path.

**Rules for every feature PR:**
1. Add the feature's flag to `flags.json` in the same PR.
2. A new flag starts with `"default": false`. Change it to `true` once the feature's Verify step has passed (on real hardware, if the feature needs a camera or model). That can happen in the same PR if the PR records the check.
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

## Where the docs live

Every document except `README.md`, `STARTUP.md` and the tool-bound instruction files (`CLAUDE.md`, `AGENTS.md`, `.github/pull_request_template.md`, `.claude/`) lives in `notes/`; the index is `notes/README.md`. When a change alters behaviour, a command, a flag or a table, update the doc that describes it in the same PR: `STARTUP.md` for setup and environment, `notes/supabase.md` for migrations, `notes/PRD-cues.md` §17 for shared data, `notes/outstanding-work.md` for what is still open.

## Product rules every change must respect

These come from the PRD and are not optional.

**Privacy**
- Camera frames, images and raw camera data never leave the station laptop. Only structured events go to Supabase, the LLM, or Photon. The privacy claim is "student camera images and video stay local". Don't claim that all audio stays on-device (teacher voice may use a hosted speech service).
- No face recognition or other biometric identification. A seat is identified only by its position in the camera frame.
- Gesture templates stay on the laptop in `vision/templates/` and are git-ignored, with no exceptions. The built-in gestures (thumbs up, open palm, pointing, peace, fist) use MediaPipe's own recogniser and need no template file; a teacher-recorded gesture and its catalog entry (`custom_gestures.catalog.json`) are stored there too.
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
- If the LLM call fails or times out, the failure is logged and isolated: no review is fabricated and nothing is written for it (PRD §12). The teacher still sees the child's vision status; a later, stronger evaluation can try again.

**Photon**
- Messages contain the minimum necessary information only: no images or raw camera data, no expression labels, no diagnoses, no unnecessary personal details.

**Shared contracts**
- The event shape in PRD §17.1 and the tables in §17.3 are shared by all three areas. A change to them updates `vision/`, `web/`, `agent/` and PRD §17 in one PR, and the PR body records sign-off from Keith, Evan and Michelle.

## Pushing

If `git push` over SSH is refused, push over HTTPS with the `gh` login:

```bash
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u https://github.com/michelliez/cues.git <branch>
```
