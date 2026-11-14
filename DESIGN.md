---
name: Cues
description: A quiet teacher workspace with a local camera, structured observations and teacher-led review.
colors:
  background: "#ffffff"
  foreground: "#20252d"
  paper: "#ffffff"
  muted: "#f2f4f7"
  muted-foreground: "#626b78"
  line: "#e6e9ee"
  surface-hover: "#f5f7fa"
  accent: "#edf3fb"
  accent-foreground: "#173f72"
  primary: "#173f72"
  primary-foreground: "#ffffff"
  ring: "#245899"
  review: "#934d31"
  review-soft: "#fcf0e9"
  workspace: "#f8f9fb"
  video-stage: "#f0f3f7"
typography:
  display:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "clamp(28px, 4vw, 38px)"
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "clamp(28px, 3vw, 36px)"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  wordmark:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "25px"
    fontWeight: 600
    letterSpacing: "-0.04em"
  metric:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-0.03em"
  heading:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  navigation:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  control:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
  caption:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 400
rounded:
  surface: "12px"
  control: "8px"
  login-input: "10px"
  badge: "5px"
  count: "6px"
spacing:
  compact: "8px"
  control: "12px"
  row: "14px"
  section: "16px"
  panel: "20px"
  workspace: "24px"
  page: "40px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "40px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "38px"
  nav-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  login-input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.login-input}"
    padding: "12px 15px"
    height: "48px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.surface}"
  person-row:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.foreground}"
    padding: "14px 12px"
  review-label:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
  review-label-elevated:
    backgroundColor: "{colors.review-soft}"
    textColor: "{colors.review}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
---
# Design System: Cues

## Overview

**Creative North Star: "The Classroom in View"**

Cues uses the Columbia Catalog / LionPlan reference as the authority for quiet operational software: white content, cool neutral framing, upright Inter, navy selection and compact rounded controls. A persistent workspace rail gives classroom monitoring, people, teacher reviews and notifications a clear home. The camera and review queue carry the work; activity controls open only when requested. This code-led reference adaptation supersedes the earlier Nexus mesh tiles and italic type, and makes no pixel-exact reproduction claim.

The sign-in surface is focused and friendly: one question at a time beneath an illustrated Cues companion. The character belongs to the product, never to a teacher profile or learner identity. Its animation supports the interaction without changing what the system knows. Structured state, honest unavailable states, position-based identification and teacher authorization remain product boundaries rather than decorative implications.

**Key Characteristics:**
- White and cool-neutral surfaces with navy actions and selection.
- Upright Inter, fine borders and compact rectangular controls.
- A persistent desktop rail that becomes a compact mobile header/navigation.
- Scan-friendly people rows and progressive activity disclosure.
- A browser-rendered login companion with restrained gaze and a sleeping password state.

Sources: `web/app/globals.css`, `web/app/layout.tsx`, `web/components/dashboard.tsx`, `workspace-sidebar.tsx`, `local-classroom-feed.tsx`, `teacher-login.tsx`, `login-companion.tsx` and `web/app/login/page.tsx`. The approved direction is `.impeccable/teacher-workspace.md`; functional boundaries are in `web/UI_REDESIGN.md`. `PRD-cues.md` remains product authority. This document records the implemented visual system.

## Colors

The frontmatter owns reusable color values. Navy is the primary action, wordmark and selected-navigation color; the pale blue accent marks selected people rows. White content sits beside a cool near-white workspace rail and login canvas. Neutral ink carries primary text, muted foreground supports context and privacy copy, and fine cool-gray lines separate rows and panels. The video placeholder uses its own quiet neutral field; connected frames use a dark contained viewport.

Warm brown review text on a pale warm fill distinguishes elevated review priority. Normal badges remain neutral. Live-connection green is specific to connection status and is not a learner-status scale. There are no colored person tiles or mesh gradients in the current interface.

**The State Comes From Text Rule.** Color supports explicit labels; it never establishes task difficulty, learner identity or an emotional diagnosis.

## Typography

Inter is loaded through `next/font/google` at weights 400, 500, 600 and 700, with Arial and sans-serif fallbacks. All visible operational and login type is upright. The frontmatter records the implemented roles: a regular login display, a medium workspace headline, semibold section headings, medium tabular summary counts, compact navigation and small supporting captions. No separate display or monospace face is used.

Workspace titles use tight tracking; body copy stays plain. Main panel headings are compact (14px overrides within panels), while the camera toolbar inherits the heading role. Login questions use the display scale; at the mobile breakpoint they settle at 29px. Person labels use medium 13px text, state uses 12px, and activity uses 11px. Match scores and timestamps belong in selected details rather than competing with the principal status.

**The One Typeface Rule.** Use upright Inter throughout the workspace and login; hierarchy comes from size, weight and spacing.

## Layout

The desktop workspace has a fixed left rail (232px), with a matching shell inset. Main content has a maximum width of 1420px and page padding of 30px 40px 28px. A breadcrumb and title precede four observed-state summary counts, separated from the working area by a rule. Current activity stays visible; Manage activity opens a right-aligned disclosure containing existing session controls and unavailable feedback.

The camera/people column and review/detail panel use a 1.8:1 grid with a minimum 290px right column and 24px gap. The camera retains a 4:3 viewport and contains frames without cropping. People appear as full-width divided rows: position label, task state, activity and SIM provenance. The right panel alternates between queue, person details and review evidence. Long facts wrap rather than expand the page.

At 1200px the rail narrows to 210px, main padding becomes 28px, and the grid tightens to 1.45:1 with an 18px gap. At 1000px the monitor becomes one column and the review panel follows the camera/people content. At 700px the rail becomes a non-fixed, wrapping header with wordmark, account shortcut when enabled, Notifications and horizontal classroom/people/review links. Desktop workspace identity, account detail and privacy block are hidden; the camera footer and page copy retain privacy context. Mobile main padding is 24px 20px. Metrics remain four compact columns; people rows move activity below label and state, with SIM alongside.

Login is a full-height column with top navigation, a centered content region (maximum 680px), a companion, one question and a form (maximum 340px). The companion reserves 132px square. Mobile header padding is 22px 24px; content remains a single centered column. Notifications has its own workspace destination and an honest coming-soon integration description.

## Elevation & Depth

The system is flat: white panels, cool framing, thin borders and subtle selected/hover fills establish containment. The activity disclosure sits above the workspace through positioning and stacking, with a border rather than a cast shadow. Keyboard focus is a two-pixel ring with a four-pixel offset; review-row focus is inset, and selected people rows have a thin inset outline.

Buttons transition background, border and press transform over 160ms with `ease`. Pressing moves a button down one pixel. Login steps arrive over 240ms using `cubic-bezier(0.23, 1, 0.32, 1)`, fading from 0.7 opacity, moving up from 8px and clearing a 1px blur. Reduced motion removes smooth scrolling, button transitions and the login entrance; the companion animation pauses and gaze centers.

**The Flat Surface Rule.** Use borders and tonal separation for containment; the current interface has no cast-shadow vocabulary.

## Shapes

Controls and navigation use compact rounded rectangles, not full pills. Panels and the local feed use the surface radius; fields have the slightly softer login-input radius. Small badges use tighter corners. People and review rows are square-edged, divided surfaces. The workspace account icon is circular; the product companion is an illustrated sphere. These exceptions express identity or character rather than a card system.

## Components

### Buttons

Primary controls use navy with white text; base secondary controls are white with neutral ink and a thin line. Primary camera actions have a 40px minimum height, login welcome 44px, login submit 46px and base controls 38px. Hover deepens navy for primary actions and uses the surface-hover fill for secondary actions. Focus remains visible; disabled controls use half opacity and a blocked cursor. Selected mobile operational actions retain a 40px minimum target.

### Inputs / Fields

Login fields are white with a cool border, 48px minimum height, 12px 15px padding and soft rectangular corners. Email and password have explicit accessible labels and autocomplete. Forms advance welcome → email → password, with reversible back/change navigation. Requests disable conflicting controls; authentication errors are sanitized. Sign-in uses existing Supabase teacher accounts, without account creation or permission assignment.

### Navigation

The rail uses compact icon/text links and a solid navy current destination. Classroom opens the dashboard, People and Teacher reviews lead to actual in-page sections, and Notifications opens `/settings/notifications`. Account access leads to `/login` only when enabled; on mobile it has a distinct accessible icon button. Inline SVG icons accompany text or accessible labels. The brand symbol is a small pair of tilted rounded bars, not a teacher avatar.

### Chips

Neutral outlined status chips communicate provenance or integration state. Review labels use a compact neutral fill by default and the warm review pair for elevated priority. SIM remains explicit text, including on mobile. Badge color never substitutes for a state name.

### Cards / Containers

Camera and review panels are white bordered containers without shadows. The camera toolbar and footer have restrained padding around a fixed-ratio video stage. The review panel uses a divided heading and clickable whole-row entries; selected evidence and structured facts replace the queue in place. Close/back actions, Escape and focus restoration support keyboard use.

### People Rows and Activity Disclosure

People are compact divided buttons (68px minimum on desktop) rather than large colored tiles. Selection uses the pale accent fill and an inset outline. Task status and tracking availability remain explicit; match scores mean gesture similarity, not probability. Manage activity uses a native details/summary disclosure and reveals only the existing gated controls. Failed writes retain confirmed state; this presentation does not deploy permissions or migrations.

### Login Companion

The Cues companion is a navy illustrated sphere with white eyes, rendered in the browser by the MIT-licensed `@bible-strong/avatar-react` and `avatar-core` packages. It is decorative and hidden from the accessibility tree. Idle gaze follows pointer position with restrained bounds and throttled updates, returning to center when the pointer leaves. Password entry puts it to sleep; busy handling requests a thinking state. Password privacy takes precedence while submitting from that step. Reduced motion pauses the character and centers its gaze. It is neither a teacher profile image nor a learner model, and no avatar builder is part of this flow.

`web.teacher_login` defaults off. With the flag off, `/login` renders an unavailable page and a classroom link without loading the companion or sign-in implementation. `web.dashboard` and existing session/review integration flags retain their separate gates. Login does not imply that persistent controls or delivery integrations are available.

The local feed loads MJPEG directly from `http://127.0.0.1:8000/stream` on the station browser. Camera frames do not traverse Supabase or the Next.js server. Only structured state feeds the workspace. Use simulated data and position labels, keep expression context from independently establishing difficulty, and require teacher approval before task or support changes. Photon is a future notification destination: no connection, delivery or credentials are implemented by this redesign.

## Do's and Don'ts

### Do:
- **Do** use navy for selected navigation and consequential actions, with explicit text labels.
- **Do** preserve the 4:3 local video viewport, SIM provenance and separate connection feedback.
- **Do** keep activity controls inside their disclosure and people in compact rows.
- **Do** retain keyboard focus, mobile account access, wrapping and reduced-motion behavior.
- **Do** treat the login companion as a product character, with password privacy and flag-off fallback.
- **Do** show only observed counts and backend-supplied reviews, with honest loading, empty, error and unavailable states.

### Don't:
- **Don't** restore glass, gradients, giant rounded tiles, heroes or oversized counts.
- **Don't** add decorative charts, imagery or an icon to every label.
- **Don't** imply dismissal resolves an alert, changes task state or applies support.
- **Don't** imply that backend history/agent assessments are already wired into the current detail panels. MJPEG is the intentional local demo transport; WebRTC is not required.
- **Don't** style tracking loss as student failure or match scores as probabilities.
