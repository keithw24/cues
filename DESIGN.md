---
name: Cues
description: A compact operational classroom monitor with local video and an attention queue.
colors:
  background: "#fff"
  foreground: "#0f172a"
  paper: "#fff"
  muted: "#f1f5f9"
  muted-foreground: "#64748b"
  line: "#e2e8f0"
  accent: "#eef8f6"
  accent-foreground: "#0f766e"
  ring: "#0f766e"
  review: "#b53c2f"
  review-soft: "#fff2ee"
  review-border: "#f1cbc3"
  hover: "#f1f5f9"
  review-hover: "#ffe9e1"
  video-placeholder: "#f8fafc"
  live: "#0f766e"
typography:
  wordmark:
    fontFamily: "Courier Prime, monospace"
    fontSize: "22px"
    fontWeight: 600
    letterSpacing: "-0.04em"
  heading:
    fontFamily: "Courier Prime, monospace"
    fontSize: "14px"
    fontWeight: 600
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Courier Prime, monospace"
    fontSize: "14px"
  control:
    fontFamily: "Courier Prime, monospace"
    fontSize: "13px"
    fontWeight: 500
  label:
    fontFamily: "Courier Prime, monospace"
    fontSize: "12px"
rounded:
  surface: "8px"
  control: "6px"
  status: "4px"
spacing:
  seat-gap: "8px"
  compact: "12px"
  panel: "16px"
  item: "20px"
  page: "24px"
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  seat-item:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  seat-item-review:
    backgroundColor: "{colors.review-soft}"
    textColor: "{colors.review}"
    rounded: "{rounded.control}"
  attention-panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.surface}"
---

# Design System: Cues

## Overview

**Creative North Star: "The Classroom Monitor"**

The user's operational brief establishes the layout; the latest admin screenshot references refine its white, navy, cool-gray, teal and coral palette. Cues is calm, compact and aligned: a neutral page, white surfaces, thin dividers, Courier Prime typography and restrained status color. The live classroom feed dominates; the attention list directs the teacher to seats needing review.

A compact seat strip selects details in the right panel. Normal task states remain quiet. There is no hero, decorative imagery, large numeric summary, glass treatment or analytics chart.

**Key Characteristics:**
- Dominant local video beside a compact attention queue.
- Neutral canvas, white surfaces and one-pixel boundaries.
- Small Courier Prime labels and compact rectangular controls.
- Strong emphasis reserved for Needs Review and selected-seat focus.

Source: `web/app/globals.css`, `web/app/layout.tsx`, `web/components/dashboard.tsx` and `web/components/local-classroom-feed.tsx`. `PRD-cues.md` remains product authority; implementation limits are recorded in `PRODUCT.md`.

## Colors

Frontmatter values are normative. White canvas and surfaces use cool-gray boundaries, navy primary text and muted slate secondary text. Teal identifies selection, keyboard focus and explicit live text. Coral marks review labels, review seat backgrounds and their borders; normal task states keep neutral text. There are no status dots or label icons. `muted` is a background token; secondary text uses `muted-foreground`. `accent` is a soft teal background; focus and selection use `ring`.

**The Review Emphasis Rule.** Needs Review receives the strongest task-state treatment; status text always accompanies color. Tracking loss remains a quiet observation state.

## Typography

Courier Prime loads through `next/font/google` in regular and bold weights, per the user’s typewriter-font request. Body text is 14px. The wordmark is 22px semibold; functional panel headings are 14px semibold. Controls and attention text are 13px; seat labels/details are generally 12px. Secondary metadata is 10–11px, and SIM is 9px. Counts and observation timestamps use tabular numerals. There is no display-type or oversized heading role in this dashboard.

## Layout

A white 58px header contains Cues, current activity, connection status and the disabled End session control. The centered main workspace has a 1680px maximum width and 16px top, 24px horizontal and 12px bottom padding. A compact toolbar precedes the monitor.

The desktop grid is approximately 70/30: `minmax(0, 7fr)` video/seat area plus `minmax(280px, 3fr)` attention/details, with a 16px gap. Video height is `clamp(280px, calc(100svh - 360px), 600px)` and uses contain fitting. Seat items sit below it in an auto-fit grid with a 160px minimum width and 8px gaps. The right surface alternates between the queue and selected seat details.

- **At 1050px and below:** main/header insets become 16px, grid gap 12px and the right column becomes 290px.
- **At 759px and below:** the right panel moves below video and seats. Main padding is 12px. Video uses a 16:10 ratio and 260px minimum height. The header wraps, keeping its 58px minimum. Standard buttons become at least 40px tall; refresh and End session are 36px, seat items 48px. Notices/footer stack.

## Elevation & Depth

There are no gradients, shadows, blur, glass fills or glowing effects. One-pixel borders and dividers establish grouping. A selected seat uses a teal border and inset one-pixel outline. Keyboard focus uses a two-pixel teal outline with three-pixel offset; forced-colors mode preserves explicit selection and video boundaries.

## Shapes

Functional surfaces use 8px corners. Buttons, seat items, notices and empty rows use 6px corners. Review labels use 4px corners. There are no status dots or label icons. Avoid nested decorative cards.

## Components

The feed has a 40px toolbar, video/placeholder area and compact footer for activity, disconnect and privacy text. Connection status for video is independent of structured seat updates. The reusable Card primitive wraps the feed and attention surface with an 8px radius, border and white background; its default shadow is omitted. CardTitle forwards an HTML heading reference. The `cn` helper uses clsx/tailwind-merge, with shadcn token mappings and components.json configuration. No hero or beam implementation is included. Camera connection is opt-in and direct to the local vision service; it is not WebRTC.

Seat items are compact buttons with name, teacher-facing status and SIM provenance. Selecting a seat opens its current activity, match score and last observation in the existing right surface. Escape or Close details returns to the queue and restores focus to the opener when it remains mounted, or the corresponding stable seat-strip button. Dismiss and Restore focus the persistent Attention heading. Tracking loss suppresses the score. History and agent assessment use honest unavailable text.

Attention items form a divided vertical list with seat, Needs Review label, status explanation, View details and Dismiss. Dismiss hides the current observation for this visit, leaves its seat status unchanged and can be restored. A new observation may appear again. End session remains disabled because session controls are not connected.

The connect-feed action uses navy fill and white text; its hover fill is #1e293b. Buttons have subtle background-only hover transitions (100ms ease); review items keep a soft coral hover fill. There are no scale presses, entrances, loading spinners or layout animation. Loading, empty, disconnected and unavailable observations remain explicit text states. Notices distinguish retained observations from live updates.

## Do's and Don'ts

### Do:
- **Do** keep video dominant and attention easy to scan.
- **Do** use neutral white surfaces, thin borders and compact aligned spacing.
- **Do** pair status color with text and reserve emphasis for Needs Review.
- **Do** preserve local video privacy, SIM labels and honest unavailable states.
- **Do** retain keyboard focus and focus restoration from details.

### Don't:
- **Don't** restore glass, gradients, giant rounded tiles, heroes or oversized counts.
- **Don't** add decorative charts, imagery or an icon to every label.
- **Don't** imply dismissal resolves an alert, changes task state or applies support.
- **Don't** claim WebRTC, connected session controls, history or agent assessments exist.
- **Don't** style tracking loss as student failure or match scores as probabilities.
