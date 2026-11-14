# Teacher workspace and sign-in

Mode: Operate. User-pinned reference: Columbia Catalog / LionPlan onboarding and Johnathan Mo's product UI. This brief supersedes the earlier Nexus palette and italic type treatment.

Direction: quiet neutral surfaces, Inter, Columbia-like navy, compact rounded controls, a persistent workspace rail and separate destinations for classroom, people, reviews, and notifications. The classroom prioritizes camera and review context. Activity management is progressively disclosed; people use scan-friendly rows rather than large colored tiles.

Login: an animated illustrated Cues companion above one question at a time. It belongs to the product, never to a teacher profile or learner identity. The user explicitly corrected the earlier teacher-avatar interpretation. Keep it animated, respond to pointer position with a restrained gaze, rest during password entry, honor reduced motion. No avatar builder or teacher picture.

Preserve: Supabase state/realtime, position identifiers, simulated-data provenance, tracking-loss semantics, review evidence, teacher authorization, existing feature flags, and the local-only camera connection. No schema or shared-contract changes in this redesign.

Photon: /settings/notifications is an honest future destination. No delivery, connection, destination settings, credentials, or notifications are implemented by this change.

Implementation: web/app/globals.css, web/components/dashboard.tsx, workspace-sidebar.tsx, workspace-icon.tsx, teacher-login.tsx, login-companion.tsx, web/app/login/page.tsx, and web/app/settings/notifications/page.tsx. The new login is gated by web.teacher_login, default false; preview builds enable it explicitly. The dashboard remains under web.dashboard.

Sources studied: https://columbia-catalog.vercel.app/onboarding (live Safari inspection, redirected reference at lionplan.org); /private/tmp/cues-columbia-reference/components/onboarding/screen.tsx and components/shell/catalog-sidebar.tsx; https://www.johnathanmo.com/ and linked Drafted/Argue product pages; https://github.com/smontlouis/bible-strong-avatar-lab and its MIT-licensed @bible-strong/avatar-react / avatar-core packages. No Columbia source code was copied.

Quality bar: reference-like whitespace and a focused onboarding; glanceable operational workspace; explicit unavailable/loading/error states; all links have destinations; responsive at 1440 and 390. Code-led implementation with reference screenshots, not a pixel-exact comp reproduction.
