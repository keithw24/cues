# Person observations: feature one

Source: Keith's `public.seat_state` upserts through Supabase Realtime, joined to
`seats`/`activities` metadata. This is not a new video transport, task evaluator,
review generator or progress-history store. The station's native video feed is
unchanged. Keith's station is the S1 emitter; this laptop is the dashboard client.

## Flag and read projection

`web.person_observations` defaults false. Set
`CUES_FLAG_WEB_PERSON_OBSERVATIONS=1` locally, then restart/rebuild. With the flag
on, the existing seat-state SELECT adds only `tracking_valid`. Boolean and null
are accepted; unknown/missing validity is never treated as true. Flag off uses the
previous SELECT and display behavior, with no new freshness clock.

Migration 004 supplies the nullable column and simulated S1-P1..S1-P4 metadata.
The existing simulated-seat RLS policy and seat_state Realtime publication are
reused. Empty person metadata is not a card. No observation rows are seeded.

## Agreed display behavior

- Fresh, explicitly valid tracking: show backend task status and match score.
- Fresh tracking_valid=false: Tracking unavailable; suppress the score and task
  status emphasis. Explicit backend tracking_lost is labeled Tracking lost.
- Fresh unknown validity: Tracking unknown; no current task status/score.
- Five seconds without a fresh timestamp, a disconnected/read-error feed, or a
  future/unusable clock observation: Updates paused; suppress current task status
  and score. A one-second display tick and visibility-resume update apply this
  cutoff; it does not record attempts or measure stalled_seconds.
- Keep lost/paused cards with Last observed metadata. An actual backend deletion
  removes the card; a reused ID replaces its current observation without appending
  another card. IDs denote positions, not persistent student identities.
- Reconnect read failures retain the last server snapshot and mark it paused;
  they do not fabricate a healthy empty classroom.
- In-progress/completed counts use current valid observations. If none are current,
  show unavailable counts rather than presenting old task statuses as current.
- Selected seat details and matching review task context use the same presentation
  rules. Trusted review assessment/status fields remain unchanged.

## Hosted setup verified November 14, 2026

The public read API exposed tracking_valid before this feature, but returned zero
person metadata rows. Applied the idempotent migration-004 operations through the
signed-in project's SQL Editor (project euouguyfakajbbbvojwe, snippet
5bcdd8ab-e3ae-4774-b739-2a0e322fe6a2). Verified the editor returned four simulated
metadata rows and the existing public read policy could read all four.

Hosted reads now expose three existing person-state rows. Their tracking validity
is null and their timestamps were over an hour old when checked. The actual hosted
read renders them as Updates paused; no fresh observation was fabricated. A native
Supabase Realtime subscription was separately checked for acknowledgement.

No service-role key was retrieved/exposed and no person observations were inserted,
updated or deleted remotely. SQL Editor execution is not a claim that Supabase CLI
migration history was populated. Registry default remains off pending team rollout.

## Verification and handoff

Unit/feed tests cover flag-off projection, validity validation, exact five-second
boundary, score suppression, disconnect/future clock handling, retained/reused IDs
and backend deletion. Browser tests cover the same UI transitions, a Realtime row
event/resync, recovery, failed reconnect retention and 1440/768/390/320px layouts.
Synthetic event/REST fixtures are isolated from deployed data; actual hosted reads
and channel acknowledgement are identified separately.

Keith-side final check: emit a fresh structured S1-P1..P4 SeatState into this project
with a real tracking_valid boolean and observation timestamp, and watch the card
recover from Updates paused. Then verify valid → invalid → tracking_lost → valid
on his station. Keep camera frames local. Only simulated hackathon data is allowed.
This final fresh-emitter event cannot be claimed verified from old stored rows.

Final checks: 48 frontend tests, lint, TypeScript/build and 3 registry checks pass;
flag-on/off browser checks pass. Local ignored configuration enables this feature;
registry default remains false. A stable isolated feature preview is running at
http://localhost:3003 so concurrent main-preview builds cannot alter its flags.
