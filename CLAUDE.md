# Cues

Cues helps a special-education teacher see which students need help. A local camera pipeline watches simple tasks (raise hand, thumbs up, teacher-recorded gestures), a rules engine decides when an event matters, an AI agent suggests support, and the teacher approves every change. Setup, status and open work are in `README.md`.

## Repo layout

This is now a personal project (the hackathon is over), so there are no area owners and no
sign-offs. Any task may edit any folder.

| Area | Folder |
|---|---|
| Vision service (camera, MediaPipe, HSEmotion, task events) | `vision/` |
| Dashboard, app backend, Supabase product integration | `web/`, `supabase/` |
| Agent / routing, rules engine, Deep Agent, LLM integration, Photon | `agent/`, `cues/` |
| Shared contracts and helpers: CI, this file, feature flags | `shared/`, `.github/`, `CLAUDE.md`, `flags.json`, `.claude/agents/` |

## Environment

One shared Python environment for the whole repo, `pyproject.toml` and `uv.lock` at the root, Python 3.11 (`.python-version`). Run `uv sync` once. Add Python dependencies only to the root `pyproject.toml` with `uv add`; don't create per-folder Python projects. Secrets go in the root `.env`; copy `.env.example`. The vision service reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from it. Optional vision settings, also in `.env` or the shell: `CUES_CAMERA_INDEX` (webcam number, default 0), `CUES_CAMERA=fake`, `CUES_STATION_ID` (dev/test override only: normally the signed-in teacher's dashboard sends the station to `POST 127.0.0.1:8000/config`; with the override set, vision refuses any other station) and `CUES_SESSION_ID` (legacy/smoke commands only: with the session lifecycle on, which the launcher does by default, vision follows the station's active session from Supabase). The web app has its own `web/package.json`.

## Commands (vision)

Run from the repo root.

Checks. There are no unit tests. CI (`.github/workflows/ci.yml`) starts a local Supabase in Docker and runs two suites, and a skipped test fails the job:

| Suite | What it proves |
|---|---|
| `tests/contract` | Every column and RPC call in the code exists in the real schema, the Python contracts fit their tables, and what Python produces is accepted by the dashboard's TypeScript parsers |
| `tests/smoke` | The whole workflow works end to end: vision follows a session, a stalled child becomes a review, the teacher text is built, the dashboard reads it back, Mark as reviewed closes it |

Both need Docker and the Supabase CLI. Locally, from the repo root:

```bash
supabase start                 # once; applies every migration and the seed
uv run pytest tests            # contract + smoke (about 10s)
uv run pytest tests/contract   # or one suite
uv run pytest tests/smoke -s
(cd web && npx next typegen && npx tsc --noEmit && npm run lint && npm run build)
uv run ruff check vision shared agent tests
```

Fix formatting (rewrites files): `uv run ruff format vision agent shared tests`

Run the service and tools:

```bash
uv run uvicorn vision.app:app          # service: /stream, /health, /config, /gestures, /templates
uv run python -m vision.events --demo  # send one test event
```


## Workflow

Work happens on the `refactor` branch (cut from `main`). Keep each commit scoped to one change.
What gates a change:

1. The commands above pass, in particular the two cross-component suites:
   - **Contract tests** (`tests/contract/`): every producer and consumer of shared data (vision
     events, `seat_state`, RPC arguments, selected columns, TypeScript parsers) agrees with the
     Python contracts in `shared/` and with the live database schema.
   - **Smoke test** (`tests/smoke/`): the whole workflow end to end on the local Supabase.
   Both need `supabase start` (Docker). They are skipped, loudly, when it is not running.
2. Add a contract or smoke check for anything that crosses components, not a unit test.
3. Every new feature ships behind a feature flag (next section).
4. Merge to `main` only with CI green. `/code-review` is available when a second look helps.

## Database traffic

A hosted request costs 100-300 ms (about 5 ms locally), so never add a request per row, per person or per frame. The rules that keep it smooth:

- **Writes go through `vision.events.Emitter`:** latest seat state wins, one batch per flush, bounded queue, an 8 second request timeout (`shared/supabase_client.py`). Never call `table(...).upsert` from a stage.
- **Polling is one request per loop:** vision uses `station_tick`, the agent uses `station_snapshot`. Add what a loop needs to those functions instead of adding a second poll.
- **The dashboard applies realtime rows** (`web/lib/dashboard-feed.ts`); a full reload is only for first load, reconnect or an unseen seat.
- `tests/smoke/test_slow_database.py` fails if the writer builds a backlog at 300 ms latency.

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
- Every entry has `description` (text), `default` (true or false), `owner` and `ticket`. 

**Override.** An environment variable overrides the default: the flag name in upper case, with dots replaced by underscores, prefixed with `CUES_FLAG_`. Example: `CUES_FLAG_VISION_HANDS=0` turns hand tracking off.
- `1` or `true` means on; `0` or `false` means off; any other value is an error.
- The web app reads `NEXT_PUBLIC_CUES_FLAG_...` for flags the browser needs. If both forms are set, `CUES_FLAG_...` wins on the server.

**Reading flags.** Each area has one helper and only reads flags through it: `vision/flags.py`, `agent/flags.py`, `web/lib/flags.ts`. Each helper reads `flags.json`, applies the overrides, and treats an unknown flag name as an error.

**Status:** `vision/flags.py` exists. The vision stage and route loaders skip modules whose `FLAG` is off, and `/health` lists every vision flag's current value. `web/lib/flags.ts` exists too. `agent/flags.py` is not built yet: the agent worker reads its flag (`agent.live_progress`) through `vision/flags.py`. Until `agent/flags.py` exists, an agent feature either reuses that helper or ships with a flag-off fallback path.

**Rules for every feature PR:**
1. Add the feature's flag to `flags.json` in the same PR.
2. A new flag starts with `"default": false`. Change it to `true` once you have checked it works (on real hardware, if the feature needs a camera or model). That can happen in the same PR if the PR records the check.
3. When the flag is off, the feature's code does not run, and everything else still starts and works. Two patterns:
   - **A whole module** (a stage or router in `vision/`): the module sets `FLAG = "vision.<feature>"`, and the loader skips it when the flag is off.
   - **A behaviour inside code that always runs** (for example, sending events to Supabase instead of only to local files): check the flag where the choice is made. The flag-off path is the fallback.
4. Check the flag-off path still starts and works: run `tests/smoke` with the flag set to `0`, or extend it.
5. Infrastructure that every feature needs (the service skeleton, CI, the flag helper itself) does not get a flag.

## Docs

Only two documents: `README.md` (what Cues is, how to run it, current status and open work) and this file (rules for working in the repo). When a change alters behaviour, a command, a flag or the open-work list, update `README.md` in the same commit. Don't add other `.md` files.

## Product rules every change must respect

These are the product's non-negotiables.

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
- If the LLM call fails or times out, the failure is logged and isolated: no review is fabricated and nothing is written for it The teacher still sees the child's vision status; a later, stronger evaluation can try again.

**Photon**
- Messages contain the minimum necessary information only: no images or raw camera data, no expression labels, no diagnoses, no unnecessary personal details.

**Shared contracts**
- The event, `seat_state`, session and review shapes in `shared/contracts.py` and the tables in `supabase/migrations/` are shared by vision, web and agent. A change to them updates all three in one commit, and `tests/contract/` must pass: it is the sign-off.

## Pushing

If `git push` over SSH is refused, push over HTTPS with the `gh` login:

```bash
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u https://github.com/michelliez/cues.git <branch>
```
