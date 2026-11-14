# Cues teacher dashboard

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
Apply the migrations in `../supabase/README.md` before seeding. Then run
`npm run dev` and open http://localhost:3000.

`web.dashboard` defaults off. The server evaluates flags before importing the
client dashboard, so the off route makes no dashboard subscriptions or video
requests. Overrides accept `1`, `true`, `0`, `false`; `CUES_FLAG_WEB_DASHBOARD`
wins over `NEXT_PUBLIC_CUES_FLAG_WEB_DASHBOARD`. Restart after configuration
changes. Production builds evaluate flags/public configuration at build time.

## Local classroom feed

No WebRTC component or signaling service exists in this checkout. The frontend
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
- Attention lists only `review`/`needs_help` observations, support first. It does
  not invent a stall duration or read private alert/agent tables.
- **Dismiss** hides that observation for this browser visit only. The stored
  status and seat strip remain unchanged. A new timestamp/status can appear
  again. **Restore dismissed items** restores the local list.
- Seats and **View details** open the same side panel. Escape/Close returns focus
  to the original seat button, or that seat's stable strip button when the queue
  opener has been unmounted. Dismiss/restore return focus to the Attention heading.
- Status labels are Ready, Working, Completed, Needs Review and Tracking Lost.
  Tracking loss is unavailable observation, not task failure. No Improving status
  is invented without a supporting contract.
- Match score and observation time live in details. Lost tracking/missing scores
  show Unavailable. No fabricated observations fill loading or empty views.
- End session is visibly disabled: no session-write endpoint exists. Activity
  controls, persistent alert dismissal, approval actions, progress history, stall
  duration, and agent assessments require their actual integrations. No backend
  code or shared event/table contracts were changed for this redesign.

## Verification

From `web/`:

```bash
npm run lint
npm test
npm run build
```

Ten automated tests cover contracts, missing/invalid data, flags, subscription
refresh/recovery/disposal, and observation-scoped dismissal. Isolated Chrome
verified actual Supabase reads/realtime, native keyboard selection and refresh,
focus restoration, direct synthetic MJPEG playback/disconnect/error/retry, and
attention/dismiss/restore using browser-only intercepted synthetic state. No
Supabase rows were modified. The layout was checked from 320–1440px: video takes
about 69% of the laptop workspace and attention moves below it on mobile.

Physical camera/model behavior, actual WebRTC, authenticated session/alert writes,
and physical touch-device testing remain unverified or unimplemented as above.

## UI components and reference palette

TypeScript and Tailwind4 were already configured. Reusable presentation primitives
now live in `web/components/ui/`, separate from the data-aware dashboard and local
feed components in `web/components/`. `@/components/ui` points there through the
existing TypeScript alias; `web/components.json` configures the shadcn-compatible
paths and `app/globals.css`. See [shadcn configuration](https://ui.shadcn.com/docs/components-json).
No framework reinitialization is needed.

The supplied Card primitives are integrated into the classroom feed and attention
surfaces in `components/ui/card.tsx`. Their heading ref type is corrected, shadows
are removed, and `lib/utils.ts` provides `cn` using clsx/tailwind-merge. Both package
manifests are updated. The attachment references `Hero195` but supplies no such
implementation, so no broken demo/hero route was added. Its unused Radix widgets,
border beam, animation pack, stock images, and additional font families were not
installed; the requested interface uses normal Courier Prime and no decorative icons.

The palette draws from the supplied admin screenshots: white surfaces, navy text,
cool gray dividers, teal selection/live text, and muted coral for Needs Review.
Live state remains explicit text; status dots are removed.
