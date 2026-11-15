# Teacher workspace redesign

The workspace now matches the landing page demo and shares tokens with the
landing (Night) and sign-in (light) pages. `notes/DESIGN.md` at the repo root records
the system; `notes/teacher-workspace-alignment-spec.md` records the decisions.

## What changed

- `/dashboard`: plain header (title and session controls), then the
  camera (16:9) beside one Class list. Needs you is pinned first; rows open in
  place with the review decision and a "Why did Cues ask?" disclosure.
- Signed out, `/dashboard` shows a sign-in card instead of errors.
- `/live` and `/settings/stations` (camera pairing) redirect to `/dashboard`;
  `/settings/notifications` redirects to `/settings/profile#notifications`.
- The rail holds Classroom, Profile and the theme toggle.
- The login and sign-up header uses the landing nav's box, so the logo does not
  move between pages.
- Fixed: the Profile form stayed on "Loading your profile…" when signed out.
- Removed flags: `web.room_view`, `web.live_view`.

## Verification

- `npm run lint`, `npm run test` (141 passing), `npm run build`.
- Browser (dev server, flags from `.env.local`): signed-out dashboard, profile,
  redirects, landing demo, logo position on `/`, `/login`, `/signup` at 1440px.
  Signed-in states were checked on a temporary page with simulated people
  (deleted): light and dark, 4 and 18 students, an opened request, 375px.

Still needed: a check with a signed-in test teacher (review decision buttons
against the RPC), and the live MJPEG feed in the new 16:9 card with
`uv run uvicorn vision.app:app` running.
