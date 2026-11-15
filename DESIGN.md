---
name: Cues
description: A calm teacher workspace that shares one visual system with the landing and sign-in pages.
colors:
  night-bg: "#111a3a"
  night-panel: "rgb(255 255 255 / 0.045)"
  night-ink: "#eef1fb"
  night-ink-soft: "#aeb6cc"
  night-ink-faint: "#7c86a3"
  night-accent: "#8fa3ff"
  light-bg: "#f7f7f7"
  light-panel: "#ffffff"
  light-tile: "#f6f6f8"
  light-ink: "#0b0d12"
  light-ink-soft: "#6b6f78"
  light-ink-faint: "#9a9da5"
  blue: "#425cc8"
  done: "#1d6b45"
  done-soft: "#e7f5ed"
  review: "#934d31"
  review-soft: "#fcf0e9"
typography:
  display:
    fontFamily: "EB Garamond, Georgia, serif"
    fontSize: "clamp(40px, 5.5vw, 60px)"
    fontWeight: 500
    letterSpacing: "-0.015em"
  panel-heading:
    fontFamily: "Inter"
    fontSize: "20px"
    fontWeight: 500
  body:
    fontFamily: "Inter"
    fontSize: "14px"
    fontWeight: 400
  caption:
    fontFamily: "Inter"
    fontSize: "11px"
    fontWeight: 500
    letterSpacing: "0.08em"
    textTransform: "uppercase"
rounded:
  panel: "28px"
  row: "16px"
  pill: "999px"
spacing:
  panel-padding: "12px"
  gap: "20px"
  gutter: "clamp(20px, 4vw, 48px)"
---
# Design System: Cues

## Overview

Cues has three surfaces that share one look: the landing page (`/`), the sign-in pages (`/login`, `/signup`) and the teacher workspace (`/dashboard`, `/settings/*`). The workspace follows the dashboard that the landing page demo shows, so the product looks the way the marketing promises.

The direction is **very simple and uncluttered**. A screen has few surfaces, small spaced captions, pill buttons and round icon buttons. Model and technical detail waits behind a disclosure. Sources: `web/components/workspace.css`, `dashboard.tsx`, `local-classroom-feed.tsx`, `person-panel.tsx`, `workspace-rows.tsx`, `workspace-sidebar.tsx`, `landing.css`, `auth.css`. The interview that set these decisions is in `.plans/teacher-workspace-alignment-spec.md`.

## Themes

Every page has a light/dark toggle (`web.theme_toggle`). The choice is saved per browser in `localStorage` (`cues-theme`). With no saved choice, each page keeps its default: Night for the landing page and the workspace, light for sign-in.

- **Night** uses the landing page navy (`#111a3a`), see-through panels and light ink.
- **Light** uses the sign-in canvas (`#f7f7f7`), white panels and near-black ink.

`workspace.css` defines every color as a `--ws-*` token on `.dashboard-shell`, and redefines the tokens under `:root[data-theme="light"]`. The landing demo window (`.ws-demo`) always uses the light tokens.

## Typography

Inter carries all interface text. EB Garamond (`--font-garamond`) is used only for page titles ("your classroom", "Profile"), as on the landing page. Times use tabular figures. Captions are 11px, uppercase, with 0.08em spacing.

## Layout

**Rail.** A 76px column of 44px round buttons: Classroom and Profile, with the theme toggle at the bottom. Each button shows its name on hover and keyboard focus. Below 700px the rail becomes a sticky top bar.

**Classroom (`/dashboard`)**, top to bottom:

1. **Header.** No banner: the page background with one soft blue glow, the "your classroom" title and the session controls (activity picker, Start or Change activity, End, refresh).
2. **Camera and Class, side by side.** The camera card takes about 60% of the width, and the Class list sits beside it. Below 1000px they stack, with the Class list first.

**Camera card.** The stage is always 16:9, the camera's own shape, so a live frame fills it with no black bars. The column sets the size; the video never does. Off, the stage shows "Turn on video". Live, it shows the vision service's MJPEG (Motion JPEG) stream from `http://127.0.0.1:8000/stream`, including the service's own overlay (a box and label per person, hand points). The header shows only "Camera", plus a Turn off button while live. The browser remembers in `localStorage` (`cues-video`) that the teacher turned the video on.

**Class list.** One list replaces the earlier People and Needs you panels:

- **Needs you** comes first. It holds one row per person with a pending review, in queue order (elevated priority first, then oldest). A person stays here even after leaving the camera's view, and the row then says "Not in view".
- **Everyone else** follows: the other people the camera sees, left to right, each with a status pill. This label appears only when a Needs you group exists.
- When nobody needs the teacher and reviews are connected, one green "All clear" line replaces the Needs you group.
- Rows show the activity name only when the class is on more than one activity.
- On desktop the list stays in view, keeps to the screen's height and scrolls inside itself, so a large class never makes the page long.

**Opening a person.** A row opens in place and closes with a second click or Escape. It shows the status in one sentence. For a pending review it also shows "Student may need support", a short plain explanation, the two decisions (Support needed, No support needed) and a closed "Why did Cues ask?" disclosure. The disclosure holds the agent's rationale and the evidence types it used.

**Signed out.** The Classroom shows one centered card with the Cues companion, "Sign in to see your classroom" and a Sign in button. It shows no error banner and no empty panels.

**Profile (`/settings/profile`).** A Garamond title and a single column of panels: account and sign-out, name and alert phone, and Photon text alerts (`#notifications`).

## Shapes

Corners are concentric: an outer radius equals the inner radius plus the padding. A 28px panel holds 16px rows with 12px of padding. Buttons are full pills; icon buttons and avatars are circles.

## Motion

- Buttons scale to 0.96 when pressed (150ms, ease-out). Disabled buttons do not scale.
- On first load, the title, activity controls, camera and list arrive 100ms apart: opacity, 12px rise and 4px blur over 300ms.
- An opened row fades and rises 6px over 200ms.
- Hover styles apply only on hover-capable pointers.
- Under `prefers-reduced-motion: reduce`, movement and blur are removed.
- The theme toggle turns transitions off for the swap so colors change at once.
- **Landing hero glow drift.** The blurred glow behind the landing headline (`.ln-hero::before`) slowly turns and swells (`ln-drift`: ±5° rotation, 1.08 scale, a few percent of travel, 26s each way, `cubic-bezier(0.77, 0, 0.175, 1)`, alternating). Transform only. It runs only with `web.landing_motion`, only while the hero is on screen in a visible tab (`landing-ambient.tsx` sets `data-drift`; otherwise the animation pauses in place), and never under reduced motion. The landing page's main navy background does not move.
- The logo does not move between the landing and sign-in pages: both headers are 72px tall with a `clamp(16px, 4vw, 40px)` side gutter and a 28px mark.

## The Cues companion

The ball on the sign-in pages (`web/components/cues-blob.tsx`) uses the workspace palette rather than a flat accent: an indigo body (`#5763d2`) that leans toward the lavender in the page glow, a pale lavender rim (`#cdc8f6`), dark grain in the workspace navy (`#1d2a6a`) and a lavender drop shadow on Night. It is decorative and hidden from screen readers.

## Sign-in background

The sign-in pages (`/login`, `/signup`, `/auth/confirmed`) have a faint 22px dot grid (`.auth-page::before` in `web/components/auth.css`): 1px dots at 13% ink on light and 12% white on Night. A radial mask fades it out behind the companion and the question, so it only shows toward the edges. It does not move. The classroom stays plain.

## Color rules

- **Text names the state.** Status pills always carry a word (Working, Finished, Needs you, Urgent). Color only supports the word.
- **Blue** marks Working. **Green** marks Finished and "All clear". **Warm brown** marks requests and Urgent. No color implies a learner's feelings or ability.

## Product boundaries the design keeps

- Video stays on the laptop. The browser reads the loopback stream directly, and no frame passes through the app server or Supabase.
- Expression output never appears in the teacher's panels.
- Teacher decisions go through the `resolve_teacher_review` RPC (remote procedure call). The dashboard does not hide reviews locally as a stand-in for a decision.
- People are named as the backend names them ("Person 1"). Only simulated students are used.

## Removed in this redesign

- **`/live`** now redirects to `/dashboard`. Its people, counts and review decision now live on Classroom. Its "decision noted on this screen only" path is gone, because a decision that is not saved contradicts the review model.
- **`/settings/notifications`** said "Coming soon" although Photon alerts already work. It now redirects to `/settings/profile#notifications`.
- **Room view, "Who needs you next" card and "Last hour" timeline.** The timeline plotted only pending reviews, so resolved items disappeared and it read like history when it was not.
- **Raw station, session and owner IDs** in the session controls.
- **The numbers row** (In view, Working, Finished, Need you). The Class list already shows each of these: the Needs you group and its count, each person's status pill, and who is in view.
- **Camera pairing.** `/settings/stations` (a pairing-code form) now redirects to `/dashboard`. A teacher's classroom is created on first sign-in, and the dashboard tells this laptop's vision service which classroom it belongs to (`POST 127.0.0.1:8000/config`), so a code adds nothing. The Supabase pairing RPC is left in place; no schema change.
- **Flags `web.room_view` and `web.live_view`.** Their features no longer exist.
