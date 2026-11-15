# Teacher workspace alignment spec

Interviewed with Evan on 2026-11-14 (jmo `interview` skill), then iterated live with `jmoui` and screenshots. Evan's taste: very simple, no clutter. Goal: the signed-in
app looks and behaves like the dashboard the landing page demos, uses the same
tokens as the landing (night) and login (light) pages, and only offers what the
backend actually does.

## Decisions

| Topic | Decision |
|---|---|
| Dashboard layout | Follow the landing demo window. Hero picked with jmoui: variant C, no banner (plain page, soft blue glow, Garamond title, four big numbers). The "room" view, "Who needs you next" card and drawer are removed. |
| /live | Folded into Classroom. `/live` redirects to `/dashboard`. The local-only "decision" path (noted on screen only, never saved) is removed: it contradicts the persistent review model. |
| Theme | Keep the light/dark toggle on every page. Both themes must look finished. Page defaults stay as they are (night for landing + workspace, light for login). |
| Signed out | A calm sign-in card with the Cues companion and one Sign in button. No error banner, no empty panels. |
| Review detail | Plain teacher language only: who, which task, when, "may need support", and the two decisions. Model internals (rationale, evidence) sit behind a "Why did Cues ask?" disclosure, in plain words. No expression labels or scores are shown. |
| Timeline | Removed (it plotted only pending reviews, so it read like history but wasn't). |
| Activity / session | Lives in the banner: the subtitle is the current activity, with the session controls under it. Raw station/session/owner UUIDs are removed from the UI. |
| Notifications page | `/settings/notifications` ("Coming soon") is stale: Photon works and is set up in Profile. It redirects to `/settings/profile#notifications`. |
| Camera | On the page, not behind a button: a 16:9 card (the camera's shape, so no black bars) beside the class list, sized by its column. No status caption or footer. |
| People + Needs you | Combined into one Class list: Needs you pinned first (even out of view), then everyone else. Rows open in place with the decision and "Why did Cues ask?". On desktop the list keeps to screen height and scrolls inside itself. |
| Logo | It must not move between landing and sign-in (jmo `animate`: don't animate it, align it). |

## Out of scope

Supabase schema, RPCs, agent and vision code. No new backend behaviour.

## Verify

- `npm run lint`, `npm run test`, `npm run build` in `web/`.
- Browser: landing → login → dashboard in light and dark, signed out; dashboard
  states rendered with simulated fixtures (loading, empty, people, review open,
  person open, camera sheet), desktop 1440 and mobile 390.
