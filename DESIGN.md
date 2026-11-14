---
name: Cues
description: A warm classroom noticeboard for clear task observations.
colors:
  background: "#f8f8f2"
  foreground: "#213c34"
  paper: "#fffef9"
  muted: "#5b6d65"
  line: "#d9dfd4"
  green: "#286149"
  soft-green: "#e6eddd"
  amber: "#80551d"
  active: "#427790"
  done-surface: "#f0f5e8"
  review-surface: "#fcf4e4"
  neutral-status: "#78866e"
  connection-pending: "#7b725b"
  simulation-surface: "#edf0e7"
  wordmark-period: "#5b7b43"
  selection: "#d1e2bd"
typography:
  display:
    fontFamily: "Geist, sans-serif"
    fontSize: "clamp(32px, 3.4vw, 47px)"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-.035em"
  headline:
    fontFamily: "Geist, sans-serif"
    fontSize: "27px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-.025em"
  title:
    fontFamily: "Geist, sans-serif"
    fontSize: "23px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-.02em"
  body:
    fontFamily: "Geist, sans-serif"
    fontSize: "15px"
    lineHeight: 1.6
  detail:
    fontFamily: "Geist, sans-serif"
    fontSize: "13px"
    lineHeight: 1.7
  label:
    fontFamily: "Geist, sans-serif"
    fontSize: "12px"
rounded:
  simulation: "4px"
  button: "8px"
  notice: "12px"
  card: "14px"
spacing:
  compact: "8px"
  small: "16px"
  grid-mobile: "18px"
  grid: "24px"
  card: "28px"
  section: "32px"
  heading: "48px"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.button}"
    padding: "10px 18px"
  button-hover:
    backgroundColor: "{colors.soft-green}"
  simulation-chip:
    backgroundColor: "{colors.simulation-surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.simulation}"
    padding: "5px 7px"
  seat-card:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.card}"
    padding: "28px"
  seat-card-done:
    backgroundColor: "{colors.done-surface}"
  seat-card-review:
    backgroundColor: "{colors.review-surface}"
  notice:
    backgroundColor: "{colors.review-surface}"
    rounded: "{rounded.notice}"
    padding: "22px"
---

# Design System: Cues

## Overview

**Creative North Star: "The Classroom Noticeboard"**

Warm paper, green ink and generous space give structured observations a familiar classroom setting. Status labels lead each seat card; small facts and timestamps support the teacher’s quick scan. The visual tone is calm, practical and attentive.

The system uses restrained borders and flat surfaces. Its identity comes from the cream canvas, compact three-stroke wordmark and carefully stepped typography. Connection health stays in the page heading, separate from each seat’s task status.

**Key Characteristics:**
- Warm paper surfaces and green ink.
- Status-led cards with text alongside every status dot.
- Flat containers with restrained borders.
- Quiet metadata and clear simulation labels.

Evidence: extracted from `web/app/globals.css`, `web/app/layout.tsx`, `web/components/dashboard.tsx` and `web/lib/dashboard.ts`. This records implemented code; screenshots and computed styles were not available during extraction. `PRODUCT.md` supplies product context; `PRD-cues.md` remains product authority.

## Colors

The palette combines warm neutrals with green identity accents and a small set of task-state colors. Frontmatter values are normative.

### Primary
- **Classroom Green** (`green`): wordmark strokes, live connection dot, completed-task dot, focus outlines and button borders.
- **Soft Leaf** (`soft-green`): button hover fill.
- **Wordmark Leaf** (`wordmark-period`): the wordmark’s final punctuation.

### Secondary
- **Observation Blue** (`active`): the in-progress dot.
- **Review Amber** (`amber`): review/support status text and dot.
- **Review Paper** (`review-surface`): review/support cards and connection/error notices.
- **Completion Paper** (`done-surface`): completed-task cards.

### Neutral
- **Cream Canvas** (`background`): page background.
- **Paper** (`paper`): default cards and skip link.
- **Green Ink** (`foreground`): primary text and wordmark.
- **Quiet Ink** (`muted`): explanatory copy, labels and timestamps.
- **Pencil Line** (`line`): card boundaries and section dividers.
- **Sage Marker** (`neutral-status`): idle, tracking-paused and missing-observation dots.
- **Pending Marker** (`connection-pending`): connection dot before a live connection is established.
- **Simulation Paper** (`simulation-surface`): SIM badge fill.
- **Selection Leaf** (`selection`): selected text background.

**The Separate Signals Rule.** Connection health belongs in its own labeled indicator. It must not recolor a seat as though the student’s task state changed.

## Typography

**Display and Body Font:** Geist, with sans-serif fallback, loaded through `next/font/google`. Geist Mono is loaded and exposed as a font variable but has no explicit component role in this dashboard.

**Character:** A compact, plain-spoken sans-serif hierarchy. Medium weight carries task and seat emphasis; smaller quiet text carries supporting context. Tight negative tracking is reserved for prominent headings and the wordmark.

### Hierarchy
- **Display:** the responsive page title; balanced wrapping.
- **Headline:** the seat’s task status; visually stronger than its seat name.
- **Title:** seat names; the overview title uses a smaller size (21px).
- **Body:** heading support copy. Activity facts also use this size, with medium weight.
- **Detail:** task explanations, limited to 46ch; notices use larger copy (14px), limited to 65ch.
- **Label:** connection state, fact labels and station metadata. Card/footer timestamps use smaller text (11px) and tabular numerals. SIM uses uppercase text (10px) with spaced letters (.06em).

## Layout

The dashboard is a full-height vertical shell. Header and footer use viewport-relative horizontal padding (5vw); the centered main area is capped (1180px) and otherwise occupies 90vw. Main top/bottom padding is 65px/80px. The heading pairs a left title with a right connection indicator and leaves a large gap before the overview.

Stations form vertical groups. Each station heading has a top divider and two equal-width seat columns with a 24px gap. Cards use 28px internal padding, a spacious heading-to-status gap (36px), a divided facts row and a divided timestamp footer. Explanatory observation copy is limited to 75ch. Long seat/activity text can wrap anywhere.

At viewport widths of 760px and below, the grid becomes one column with an 18px gap; card padding becomes 24px. The page heading stacks, with connection health below it; main top padding becomes 38px. The header description disappears, notices stack their content and action, and the footer becomes a column. The overview annotation narrows to 150px and remains right aligned.

## Elevation & Depth

The implemented system has no shadows, gradients or blur. Paper tones, one-pixel dividers and whitespace establish grouping. A completed or review card changes its surface tint without gaining elevation.

**The Flat Paper Rule.** Preserve tonal surfaces and fine borders as the default grouping language.

## Shapes

Cards have gently curved corners; notices are slightly tighter, buttons tighter again and SIM badges nearly square. Status marks and connection dots are circular. Borders use a single thin stroke. The wordmark’s three rounded vertical strokes have differing heights; the terminal dot adds a small leaf-colored accent.

## Components

### Buttons

Quiet outlined controls support reconnecting and refreshing.
- Green border, transparent fill, green-ink text and button-radius corners; minimum height (44px).
- Hover adds the soft leaf fill with a background-color transition (150ms ease-out).
- Keyboard focus uses a green outline (3px) with offset (5px).
- Disabled controls lower opacity (.55) and use the wait cursor.
- No filled primary variant is implemented.

### Chips

The SIM badge is a small, quiet provenance label, not an action. It sits beside the seat name and has additional screen-reader text identifying a simulated seat.

### Cards / Containers

The seat card is the signature pattern: seat identity and SIM first, large task status second, explanatory copy third, then activity and match score, followed by seat ID and timestamp. A colored dot always accompanies a text status. Completed cards use completion paper; review and support share review paper and amber labels. Active state changes the dot only. Tracking-paused and idle states retain neutral styling. A missing observation has its own plain-language label.

### Navigation

The only implemented navigation is the home-linked Cues wordmark and the focus-revealed skip link. The header’s teacher-dashboard label is informational. No sidebar, tabs or navigation menu is implemented.

### Connection and notices

The compact labeled connection indicator occupies the heading’s trailing edge on wide screens. Its live state uses green; other connection states retain quiet ink and the pending marker. Connection/error notices use review paper, a short heading, explanatory copy and a reconnect action where available. Retained data is explicitly labeled as the last loaded state when disconnected.

### Loading and empty states

Both use spacious text regions above a thin divider. Loading adds a short green line whose width alternates (56px to 100px over 1.3s). Reduced-motion preference disables animation and transitions globally. The empty state offers a check-again action. No input fields are implemented in this slice.

## Do's and Don'ts

### Do:
- **Do** pair every task-state color with a readable label.
- **Do** keep connection health separate from task status.
- **Do** preserve SIM provenance labels and quiet timestamps.
- **Do** retain visible keyboard focus and the reduced-motion fallback.
- **Do** use flat paper surfaces, fine borders and space to group content.

### Don't:
- **Don't** style tracking loss as student failure.
- **Don't** use color alone to communicate status.
- **Don't** turn the simulation badge into an action control.
- **Don't** add shadows or filled action variants while claiming they are part of this extracted system.
