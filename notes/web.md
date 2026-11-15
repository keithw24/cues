# Cues teacher dashboard

> **Read this with the current docs.** This file started as the original read-only dashboard
> foundation and keeps its operational checks and history. The current layout and design system
> are in [DESIGN.md](DESIGN.md) and [web-ui-redesign.md](web-ui-redesign.md); the product
> framing is in [PRODUCT.md](PRODUCT.md). The flag table at the bottom is generated from
> `flags.json` and is the current list. The "UI components and reference palette" section
> describes the first design, which the workspace redesign replaced.

A compact operational classroom view: local video, an observation-based attention
list, selectable seats, and details for the selected seat. This app reads
structured state from Supabase; it does not upload camera frames or change
activities, sessions, alerts, or interventions.

## Run locally

From `web/`, run `npm ci`. Copy `.env.example` to the ignored `.env.local`, then set:

```text
NEXT_PUBLIC_SUPABASE_URL=<project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<sb_publishable_... key>
CUES_FLAG_WEB_DASHBOARD=1
```

Use only a publishable key, never a service-role key in browser configuration.
Apply the migrations in `notes/supabase.md` before seeding. Then run
`npm run dev` and open http://localhost:3000.

`web.dashboard` defaults off. The server evaluates flags before rendering the
client dashboard (it is imported statically: a dynamic import made `next dev` log "Could not validate `instant`"), so the off route makes no dashboard subscriptions or video
requests. Overrides accept `1`, `true`, `0`, `false`; `CUES_FLAG_WEB_DASHBOARD`
wins over `NEXT_PUBLIC_CUES_FLAG_WEB_DASHBOARD`. Restart after configuration
changes. Production builds evaluate flags/public configuration at build time.

## Local classroom feed

MJPEG is the intentional local demo transport; WebRTC is not required. The frontend
uses the existing vision service's MJPEG endpoint directly from the browser:
`http://127.0.0.1:8000/stream`. It is not proxied through Next.js or a cloud API.
The dashboard must be opened on localhost/127.0.0.1 on the station laptop.
The feed starts only after **Connect local feed**, and supports disconnect,
connection errors and retry. Seat updates remain independent of video health.

From the repository root, start the existing camera-free service for a demo:

```bash
uv sync
CUES_CAMERA=fake CUES_FLAG_VISION_SUPABASE_EVENTS=0 uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000
```

This displays a synthetic moving bar, not classroom footage. Real-camera/model
verification remains a separate station check. Never send student frames to
Supabase, the LLM, or another cloud service.

## Current behavior and integration limits

- Existing initial reads and `seat_state` realtime subscription are preserved.
  Reconnect reloads the snapshot; failures retain it with a visible warning.
- Attention reads only pending `teacher_reviews`, behind `web.teacher_reviews`
  (default on since 2026-11-14; `=0` turns it off). No seat-status fallback and no approval/dismissal actions.
  See [TeacherReview contract and rollout](web-teacher-reviews.md) for the expected
  projection and Michelle-side persistence/RLS/Realtime prerequisites.
- Seats and **View details** open the same side panel. Escape/Close returns focus
  to the original seat button, or that seat's stable strip button when the queue
  opener has been unmounted.
- Status labels are Ready, Working, Completed, Needs Review and Tracking Lost.
  Tracking loss is unavailable observation, not task failure. No Improving status
  is invented without a supporting contract.
- Match score and observation time live in details. Lost tracking/missing scores
  show Unavailable. No fabricated observations fill loading or empty views.
- End session is visibly disabled: no session-write endpoint exists. Activity
  controls, persistent review resolution and display of backend history/assessment context
  require frontend integration. Supabase teacher_reviews and authenticated
  resolve_teacher_review RPC already exist; local hiding is not review resolution. No backend
  code or shared event/table contracts were changed for this redesign.

## Verification

From `web/`:

```bash
npm run lint
npm test
npm run build
```

Seventeen automated tests cover contracts, missing/invalid data, flags, seat-feed
recovery/disposal, and the review projection, pending status exits/deletes,
reconnect, errors/stale data and flag-off no-network behavior. Three shared
flag-registry tests also pass.

The existing local MJPEG source was previously verified with synthetic frames.
For the new teacher_reviews integration, isolated Chrome uses intercepted REST
fixtures rather than writing Supabase: it checks fields/order, no actions,
confirmed/dismissed exits after resync, independence from seat status, error/retry,
and 4:3 landscape video with no overflow at 320, 390, 768 and 1440px. Realtime event
callbacks are exercised in unit tests. Deployed teacher_reviews persistence,
authorization and Realtime delivery remain pending Michelle-side integration;
fixture checks are not evidence of that deployment.

Physical camera/model behavior, authenticated session/review UI wiring,
and physical touch-device testing remain unverified or unimplemented as above.

## UI components and reference palette (historical: the first design)

TypeScript and Tailwind4 were already configured. Reusable presentation primitives
now live in `web/components/ui/`, separate from the data-aware dashboard and local
feed components in `web/components/`. `@/components/ui` points there through the
existing TypeScript alias; `web/components.json` configures the shadcn-compatible
paths and `web/app/globals.css`. See [shadcn configuration](https://ui.shadcn.com/docs/components-json).
No framework reinitialization is needed.

The supplied Card primitives are integrated into the classroom feed and attention
surfaces in `web/components/ui/card.tsx` (removed again by the later workspace redesign). Their
heading ref type is corrected, shadows are removed, and `web/lib/utils.ts` provides `cn` using clsx/tailwind-merge. Both package
manifests are updated. The attachment references `Hero195` but supplies no such
implementation, so no broken demo/hero route was added. Its unused Radix widgets,
border beam, animation pack, stock images, and additional font families were not
installed; the requested interface uses normal Courier Prime and no decorative icons.

The palette draws from the supplied admin screenshots: white surfaces, navy text,
cool gray dividers, teal selection/live text, and muted coral for Needs Review.
Live state remains explicit text; status dots are removed.

Persistent review action UI is available behind default-off
`web.teacher_review_actions`. Its proposed Supabase RPC and deployment prerequisites
are documented in [TEACHER_REVIEWS.md](web-teacher-reviews.md#persistent-action-adapter-supersedes-read-only-action-notes-above).
It remains disabled until authorized backend persistence and teacher authentication
are implemented. Frontend tests now total 21.

## Supplied-reference dashboard adaptation

The Cues dashboard uses the supplied Nexus HTML/CSS visual language: DM Sans,
italic headings, pill navigation, lavender canvas, cyan local video and colored
person tiles. Metrics come from loaded observations/reviews, never the reference's
sample project analytics. Reference HTML is adapted into React, not embedded as an
unconnected second dashboard.

The camera panel loads Keith's native MJPEG endpoint directly from the browser:
http://127.0.0.1:8000/stream. Run his configured local service from the repository
root with `uv run uvicorn vision.app:app --host 127.0.0.1 --port 8000`, open the
local dashboard, and choose **Connect local feed**. Connect/retry/disconnect states
are available. Remote-host dashboards intentionally cannot load the station feed.
Video remains 4:3, contains rather than stretches frames, and never goes through
Next.js, Supabase, or an LLM.

Migration `20261114000510_person_observations.sql` adds the `tracking_valid` field
Keith now emits and provisions simulated S1-P1..P4 metadata for existing demo read
policies. It creates no fabricated observations. Apply it to Supabase before
expecting person state writes to succeed. Person metadata with no state row is
hidden; once person observations exist at a station, fixed legacy seat cards for
that station are retired in the view. Person IDs remain temporary position IDs,
not student identities. Reuse/release behavior remains owned by vision.

Migration 003/session Auth setup and Michelle's teacher_reviews persistence are
still independent prerequisites. Their flags default on since 2026-11-14 (`=0` turns each off). Real progress
history remains explicitly unavailable until exposed by the backend. No missing
backend behavior is replaced with local-only demo state.

Verification: real local /stream through Keith's create_app with FakeCamera and an
empty model-stage list; isolated synthetic REST person/review fixtures; responsive
checks at 1440/768/390/320px; 33 frontend tests and a webpack production build.
This verifies video transport, not actual webcam/model inference or deployed
Supabase. Migration 004 also passed an isolated PostgreSQL application/read-policy
check alongside migration 003. No real camera or remote rows were used.

## Teacher login and workspace redesign

See [UI_REDESIGN.md](web-ui-redesign.md) for the Columbia-inspired workspace, animated
login companion, preview flags and remaining integration checks. The companion is
a product mascot on `/login`; it does not represent a teacher or student.

Person-observation feature one reads `tracking_valid` and applies the agreed
five-second display freshness rule. Lost/paused cards remain visible with their
last observation time; no frontend progress/stall decisions are made. See
[PERSON_OBSERVATIONS.md](web-person-observations.md) for the feature flag, hosted setup
verification and Keith-side fresh-emitter check.

Session controls now have deployed station-scoped Supabase actions and a prepared
vision lifecycle consumer. See [SESSION_CONTROLS.md](web-session-controls.md) for the
verified contract/security boundary and [Keith's handoff](session-lifecycle.md)
for restart and live checks. Teacher provisioning and Keith-side rollout remain;
`web.session_controls` defaults on since 2026-11-14 (`=0` turns it off). Earlier missing-contract notes
are historical. Session acknowledgement is separate from camera/model readiness.

## Web feature flags

Generated from `flags.json` (the single registry; `web/lib/flags.ts` reads it). Override any flag with
`CUES_FLAG_WEB_<NAME>=1|0` in `web/.env.local`, or `NEXT_PUBLIC_CUES_FLAG_WEB_<NAME>` for the browser.

| Flag | Default | Owner | What it does |
|---|---|---|---|
| `web.teacher_login` | on | evan | Teacher sign-in with an animated Cues companion; uses existing Supabase teacher accounts. |
| `web.teacher_signup` | on | evan | Teacher sign-up at /signup with the Cues companion; creates a Supabase account. |
| `web.alert_phone` | on | evan | Optional sign-up step that saves the teacher's mobile number (user metadata alert_phone) for Photon alerts. |
| `web.dashboard` | on | evan | Read-only teacher dashboard with Supabase seats and realtime state updates. |
| `web.landing` | on | evan | Public landing page at /; the teacher dashboard moves to /dashboard. |
| `web.teacher_reviews` | on | evan | Pending TeacherReview requests via Supabase. On the dashboard they are pinned first in the Class list as Needs you (even when the person is out of view), with the agent's rationale behind "Why did Cues ask?". Off: no requests and no rationale are read or shown. |
| `web.teacher_review_actions` | on | evan | Persistent review decisions through the resolve_teacher_review RPC (migrations 003-017, applied) |
| `web.session_controls` | on | evan | Authenticated station session lifecycle and activity controls |
| `web.person_observations` | on | evan | Read tracking_valid and show fresh, invalid, lost and paused person observations |
| `web.landing_faq` | on | evan | FAQ section and the full site footer on the landing page. When off, the landing page keeps its one-line footer. |
| `web.teacher_profile` | on | evan | Save the signed-in teacher's display name and E.164 phone number to teacher_profiles (migration 006), and move the sign-up number there after first sign-in. |
| `web.landing_demo` | on | evan | Landing hero shows a looping demo of the real dashboard (banner, People rows, review rows) with simulated students. When off, the hero keeps the older preview card. |
| `web.landing_motion` | on | evan | Landing page sections fade in once as they scroll into view. When off, every section is visible from the start. |
| `web.theme_toggle` | on | evan | Light/dark switch on the landing page, log-in, sign-up and the dashboard. The choice is saved in the browser. When off, each page keeps its default: Night for the landing page and dashboard, white for log-in and sign-up. |
| `web.vision_station_config` | on | keith | Dashboard sends the signed-in teacher's station to the vision service on 127.0.0.1:8000/config. When off, nothing is sent. |
| `web.interventions` | off | evan | Show the agent's suggested support on a review and let the teacher approve it (or pick another from the menu). Needs migration 018; approving also confirms the review. |
| `web.reset_people` | on | keith | Switching or restarting the activity puts everyone back to working: the refresh button beside Start/End restarts the current activity (finished and flagged people start over) and the requests still open are closed. Off: the button only reloads the session and switching leaves open requests alone. |
| `web.live_progress` | off | michelle | Read agent-owned evaluated progress from seat_state after migration 012. |
| `web.health_strip` | on | keith | Camera health strip on the classroom page: camera service on or off, station set, updates arriving, and another camera refused, each as its own word. Reads the local vision service on 127.0.0.1:8000 (/health, /config) and the station's writer row. Off: the page shows only its single camera-off message. |
| `web.review_page` | on | evan | To review page at /review: each person Cues asked about as a card with the activity, time, Support needed / No support needed, Mark as reviewed and "Why did Cues ask?". Adds a To review link to the rail and the classroom header. Off: /review redirects to /dashboard and no links show. |
| `web.hosted_local_feed` | off | michelle | Allow the configured hosted dashboard origin to connect directly to local vision; local-network permission and explicit backend CORS required. |

