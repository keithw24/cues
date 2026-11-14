# Cues

Cues is an AI classroom support system that uses local computer vision and an agentic workflow to surface when a student may need teacher assistance.

Built by a three-person team for HackPrinceton Fall 2026. [PRD-cues.md](PRD-cues.md) defines the MVP; this checkout contains the vision service foundation, model benchmark, event emitter, and a read-only teacher seat dashboard behind a feature flag. The complete support workflow below is the MVP target, not yet an end-to-end implementation.

## What Cues does

- The teacher selects a task or speaks a push-to-talk command mapped to a known task.
- A Logitech camera observes the student locally; MediaPipe checks hand/gesture activity and HSEmotion adds optional facial-expression context.
- Structured task-progress events sync through Supabase to the teacher dashboard.
- Rules invoke the Deep Agent only for meaningful events; it uses a configurable LLM to reason over structured context and choose support tools.
- The teacher receives dashboard alerts and optional Photon notifications, then approves any meaningful instructional change.

Facial-expression output is supporting evidence only. It never independently determines that a student is struggling.

**The LLM does not receive video frames or images.**

## Current MVP stack

| Component | Technology |
|---|---|
| Frontend | Next.js + Tailwind |
| Hand tracking | MediaPipe Hand Landmarker |
| Gesture matching | Normalized landmark nearest neighbor |
| Facial-expression context | `hsemotion-onnx` + `enet_b0_8_best_vgaf` |
| Realtime state | Supabase Postgres + Realtime |
| Agent orchestration | LangChain Deep Agents |
| LLM inference | Configurable provider and model (TBD) |
| Backend | FastAPI |
| Teacher messaging | Photon |
| Physical hardware | Logitech camera |

LLM provider and model selection is undecided; Groq and SpaceXSI are under consideration. Keep agent logic independent of provider-specific SDKs. The installed `langchain-groq` dependency is provisional and does not select a provider.

## High-level architecture

```mermaid
flowchart LR
    A[Logitech Camera] --> B[Local Vision Service]
    B --> C[MediaPipe + HSEmotion]
    C --> D[Supabase Realtime]
    D --> E[Teacher Dashboard]
    D --> F[FastAPI + Deep Agent]
    F --> G[Configurable LLM provider]
    F --> H[Photon Alert]
```

Perception runs on the station laptop. Only structured events are synced; rules invoke the agent for meaningful situations rather than every frame. The LLM never processes the video feed.

## Repository structure

| Path | Contents / ownership |
|---|---|
| `vision/` | Local FastAPI camera/pipeline foundation, model loaders, benchmark, event emitter, and tests — Keith |
| `web/` | Next.js teacher seat dashboard — Evan owns frontend, app backend, and Supabase product integration |
| `shared/` | Canonical Pydantic contracts, synthetic JSON fixtures, and contract tests |
| `PRD-cues.md` | Product requirements, architecture, shared event schema, and team responsibilities |
| `pyproject.toml`, `uv.lock`, `.python-version` | Shared Python environment |
| `.env.example` | Shared root credentials template |
| `TEAM_WORKFLOW.md` | Personal branches, ownership boundaries, and shared contract decisions |
| `flags.json` | Feature-flag registry |
| `.github/`, `.claude/agents/`, `CLAUDE.md`, `AGENTS.md` | CI, PR template, review guidance, and contributor/agent instructions |

Michelle owns agent/routing (rules, Deep Agents, LLM integration, Photon, and the agent approval workflow). Evan owns the frontend and app backend. This checkout has no `agent/` or `backend/` directory yet; its existing FastAPI entry point is `vision.app:app`.

## Development setup

Install `uv`, plus Node.js/npm for the frontend. Python is pinned to **3.11** in `.python-version`; all Python components share the root environment.

```bash
git clone https://github.com/michelliez/cues.git
cd cues
uv sync
cp .env.example .env
```

Run the local vision service from the repository root:

```bash
uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/health` for status or `/stream` for the local camera stream. For a camera-free startup, prefix the command with `CUES_CAMERA=fake`. Keep the stream on the station laptop.

Existing checks (hardware tests skipped by default):

```bash
uv run pytest vision shared/tests
uv run ruff check vision shared
uv run ruff format --check vision shared
```

The model benchmark is `uv run python -m vision.bench`; its first run downloads model weights and it uses the webcam by default.

## Frontend setup

From the repository root:

```bash
cd web
npm ci
npm run dev
```

Configure `web/.env.local` with the project URL, publishable key and
`CUES_FLAG_WEB_DASHBOARD=1` to view the simulated seat dashboard at
`http://localhost:3000`. With the flag off, the page shows a static Cues fallback.
See [web/README.md](web/README.md) for setup, realtime behavior and verification;
`npm run lint`, `npm test` and `npm run build` are available in `web/`.
Follow [web/AGENTS.md](web/AGENTS.md) before editing frontend code.

## Environment variables

The root `.env.example` contains:

| Variable | Intended use |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous client key |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged server-side Supabase key |
| `LLM_PROVIDER` | LLM provider selection (undecided) |
| `LLM_MODEL` | Model selection (undecided) |
| `LLM_API_KEY` | Credentials for the selected LLM provider |
| `PHOTON_API_KEY` | Teacher notification credentials |

The vision client loads the root `.env` and reads `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Optional settings in that file or the shell include `CUES_STATION_ID`, `CUES_SESSION_ID`, `CUES_CAMERA_INDEX`, and `CUES_CAMERA=fake`. Events go to Supabase only when `vision.supabase_events` is enabled and credentials are configured; otherwise they stay in local JSONL files under `vision/logs/`. Failed Supabase writes also fall back there.

Never commit `.env` files or secrets, and never expose service-role, LLM, or Photon keys through browser-visible `NEXT_PUBLIC_*` variables. The root template does not yet wire up the planned agent integrations.

## Contributor dependency rules

Add Python dependencies at the root with `uv add <package>` and commit **both `pyproject.toml` and `uv.lock`**. Use `uv run ...` for Python commands; do not use `pip install` as the permanent project workflow.

For frontend dependencies, run `npm install <package>` inside `web/` and commit **both `web/package.json` and `web/package-lock.json`**. Teammates install with `npm ci`. Add only dependencies needed for the task.

## Branches

Follow [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md):

| Branch | Work area |
|---|---|
| `main` | Integration / stable shared branch |
| `keith` | Computer vision / local perception |
| `evan` | Frontend / app backend / Supabase |
| `michelle` | Agent / routing / rules / LLM integration / Photon |

Work on your personal branch, keep commits small and scoped, and integrate through `main`. Follow `TEAM_WORKFLOW.md` for branch synchronization and use the PR template for review.

## Shared contracts

The agreed contracts use UUIDs for session/alert IDs, all 12 PRD event types, the PRD session/timestamp fields, `label`/`probability` for expression context, and `Activity.id` with `activity_id` on references. See `TEAM_WORKFLOW.md` §3. The `shared/contracts.py` Pydantic models are authoritative; synthetic JSON examples live in `shared/fixtures/`. See [shared/README.md](shared/README.md) for usage. The vision emitter validates and serializes these shared contracts.

## Product principles

- Assist teachers and keep their approval required before task, instruction, or support changes.
- No face recognition; no student video or images sent to cloud services.
- The LLM receives structured state only.
- Facial-expression context is supporting evidence only, never a diagnosis or a claim about how a student feels.
- Use simulated student data during the hackathon.
