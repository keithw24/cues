# Outstanding work, ranked

Written 2026-11-14 from a full pass over the PRD (§26 gaps and §25 stretch goals), the
project notes, the code, and what was left open while building. Ranked by importance:
**P0** before a demo or a merge, **P1** important, **P2** worth doing, **P3** ideas.
Owner = who normally owns that folder; effort is a rough guess (S = under a day of work,
M = a day or two, L = more).

Already done and not repeated here: one camera per station guard (see
`vision/station_lease.py` and migration 17), teacher login/profile, dynamic phone lookup,
session ownership, person-ID visibility, activity catalog alignment, Mark as reviewed,
reviews closing with their session, the "Last hour" timeline, built-in gestures.

---

## P0: before a demo or a merge

| # | Item | Why it matters | Owner | Effort |
|---|---|---|---|---|
| 1 | **Check everything on a real camera.** Pointing, peace and fist; "only the selected task can turn green"; Mark as reviewed (review disappears everywhere, child back to Working, timer restarts, a new review only after a fresh stall); a review closing when the task completes; the "Last hour" timeline with real flags; id stability (no phantom P2, returning person keeps their id); steady face and hand boxes; statuses not flipping. | All of it passed tests only. Several unticked "live check" boxes in merged PRs. | Keith | S |
| 2 | **Two laptops at once.** Keith on S1 and Michelle on S2, each signed in on their own laptop; video and sessions stay on their own station; start a second camera on S1 and confirm it is refused and the dashboard warns. | Never tried on real hardware. | Keith + Michelle | S |
| 3 | **Settle the rule breaks in CLAUDE.md.** New flags default on without a recorded live check (`vision.station_config`, `web.vision_station_config`, `vision.review_marks`); the agent changes (one open review per person, review marks) have no flag because `agent/flags.py` does not exist; shared-table changes were never written into PRD §17 or signed off. | The team's own rules say none of that should have merged as it did. Either follow the rules or change the rules. | All three | M |
| 4 | **Rotate leaked keys.** A Groq API key was printed in a terminal earlier in the build, and a Cursor API key appeared in a process listing. | Keys that were shown in logs or chat should be treated as exposed. | Keith | S |
| 5 | **Pull `main` onto every laptop and restart.** Old agent code ignores review marks and would re-flag a reviewed child; old vision ignores the one-camera guard. | Mixed code versions give confusing behaviour. | Everyone | S |

## P1: important

| # | Item | Why it matters | Owner | Effort |
|---|---|---|---|---|
| 6 | ~~**Fix the stale docs**~~ **Done 2026-11-14**: every doc moved to `notes/` (index: `notes/README.md`) and checked against the code. Original list: `STARTUP.md` (migrations "001 through 006", 006 "NOT deployed", "only the dashboard flag", "provision the session and activity manually"); `notes/supabase.md` (migrations marked "local only"/"pending" that are applied); `notes/session-lifecycle.md` (tells you to set `CUES_STATION_ID=S1`, which pins vision and defeats the dashboard handoff; "use the evan branch"); `CLAUDE.md` (T1 to T3 modules "only on their branches", flag status line, the `thumbs_up.json` exception, "same checks CI runs"); `AGENTS.md` (the `thumbs_up.json` exception); `README.md` diagram (no Mark as reviewed, no auto-close); `notes/vision-data.md` and `notes/keith.md` (no station handoff, review marks or `session_revision`; two open items that are done; test count 449 vs 609); `notes/web.md` (5 of 18 web flags); three undocumented env vars (`CUES_OVERLAY`, `CUES_PALM_FLIP`, `CUES_SPECTRUM_DEBUG`). | People follow these docs and get the wrong setup. | Keith (some files are Evan's and Michelle's) | S |
| 7 | ~~**A health strip on the dashboard.**~~ **Built 2026-11-14 behind `web.health_strip` (on by default since 2026-11-14): needs a live check on the station laptop.** Original ask: Camera on/off, station set, writes accepted, another camera refused. The dashboard now says "The camera is off" for vision off, a rejected write, and nobody in view alike. | Would have saved most of the debugging done so far. | Evan | M |
| 8 | ~~**Reviews arrive before the status changes in the demo.**~~ **Done: `demo.sh` now sets `CUES_NO_PROGRESS_SECONDS=4`.** Original note: Demo mode lets the agent request a review after 4 to 6 seconds of stalling; vision's "Needs Review" waits 30. A teacher sees a review request for a child who still reads Working. | Confusing for the audience. Align the two timers or label the demo accordingly. | Michelle + Keith | S |
| 8b | ~~**Needs Review with an empty To review tab.**~~ **Fixed 2026-11-14.** With real Supabase latency (0.5 to 0.8s per poll), the agent's 1s sleep after each read skipped a vision row every few polls; a 2.06s gap exceeded the 2s limit and reset the stall timer, so the agent never asked (session ba133be2, S1-P1 stuck for 5 minutes). The worker now polls at a fixed rate and tolerates one missed heartbeat (3s). `web.review_waiting` (on by default from #97) also lists flagged people with no request yet, and the classroom Attention panel names them instead of All clear. **To do: the live check on a station (Evan).** | | Michelle + Evan | S |
| 9 | **"Add a gesture" screen in the dashboard.** The vision API (`/gestures`, `/templates/record`) is merged; there is no screen. A created gesture also needs a database function to register it in `activities` (the browser cannot write that table), and a worker restart to pick it up. | Teacher-recorded gestures are a core promise of the PRD (§7.3, success criterion 3). | Evan (+ Keith for the database function) | M |
| 10 | ~~**CI for `web/` and `supabase/`.**~~ **Done** (`.github/workflows/web.yml` and `supabase.yml`): the web job runs install, route types, TypeScript, lint, tests and a build; the supabase job replays every migration on a real PostgreSQL and runs the SQL tests, failing if any are skipped. Still to do: watch the first runs on GitHub (they could not be run from a laptop; each step was proved on a clean checkout of `main`), and decide whether to make them required checks (see CLAUDE.md for why they are not). | | Anyone | S |
| 11 | **Database-level one-writer rule.** The one-camera guard is enforced in vision (a camera that is refused stops writing). A laptop on old code ignores it. Add a `writer_id` to `seat_state` writes and reject writes from a camera that does not hold the lease. This changes a shared table, so it needs sign-off from all three. | Closes the gap for old code and for any other writer. | Keith + all three | M |

## P2: worth doing

| # | Item | Notes | Owner | Effort |
|---|---|---|---|---|
| 12 | **Reviews keep only the first evaluation's evidence.** While a review is open, later evaluations for the same person are dropped (to avoid repeated phone notifications). The teacher never sees newer evidence. Consider updating the open review's text without re-notifying. | | Michelle | M |
| 13 | **Intervention workflow** (PRD §12, §13, §26). **Menu, suggestion and approval built 2026-11-14 behind `agent.interventions` and `web.interventions` (off); migration 018 is written and tested but not applied. Applying an approved support to a task is still not built.** The agent only requests reviews. The approved intervention menu and "teacher approves before a task or support changes" are not built; the `interventions` table is unused. | | Michelle + Evan | L |
| 14 | **Durable history.** Progress history is in memory and lost on restart; nothing records prompt history (PRD §26). | | Michelle | L |
| 15 | **Hardware and demo acceptance, deployment supervision, delivery recovery** (PRD §26). A real run-through with a failing network and a failing Photon send. | | All | M |
| 16 | ~~**Launcher hygiene.**~~ **Done: the launcher sweeps this repo's leftover processes on start and stops cleanly on SIGHUP.** Original note: Closing the terminal (SIGHUP) leaves the dashboard and worker running; a leftover `next dev` blocks the next start. Sweep leftovers from this repo on start and handle SIGHUP. The port check was fixed to ignore lingering connections. | | Michelle | S |
| 17 | ~~**Clean up old rows.**~~ **Tool built: `scripts/cleanup-seat-state.py` (dry run by default, `--delete` asks first); nothing deleted yet.** Original note: Stale `seat_state` rows from earlier layouts and test runs (`S1-L`, `S1-R`, old `S1-P*`). | | Anyone | S |
| 18 | **Timeline readability.** Marks bunch into one blob when several flags are close together. Group them and show "flagged, then reviewed" as one story. | | Evan | S |
| 19 | **Person ids are position only.** A person who leaves for over 10 seconds, or two people who swap seats, can change ids. Inherent to the no-face-recognition rule; options are a longer hold or fixed seat slots. | | Keith | M |
| 20 | **Prompt-history producer and the agent tools that read it** (PRD §12). | | Michelle | M |

## P3: ideas

- **End-of-session summary** from the flags and reviews now available (PRD stretch goal).
- **Gesture tuning screen**: record "rest" examples, adjust sensitivity per gesture, a live score meter.
- **Per-session reports** for a teacher, built on the station and ownership work.
- **Moving-gesture recognition** (DTW), **object-state tasks**, **natural-language task creation**, **local speech recognition**, **teacher analytics** (PRD §25).
- **More than one camera per classroom**: each camera as its own station, so a teacher can see more of the room. Decided 2026-11-14: **not now, keep the one-camera-per-station guard only.** If it comes back, the pieces are: a database function that creates an extra, non-default station for the same teacher; a station picker in the dashboard remembered per browser; and a one-click "use a separate station for this camera" on the laptop whose camera is being refused (its local `GET /config` reports `station_busy`). Each station keeps its own session, activity and people numbering, and the dashboard shows one station at a time unless an "all cameras" view is also built.
- **Voice controls** (PRD §14, optional).
