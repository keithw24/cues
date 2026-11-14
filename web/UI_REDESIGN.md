# Teacher workspace redesign

The Columbia Catalog / LionPlan reference guides the neutral surfaces, Inter type,
navy selection, compact controls and focused sign-in flow. The earlier colorful
Nexus tiles and repeated top navigation have been replaced by a workspace rail,
compact people rows, and a camera/review layout. Manage activity retains the
existing session controls in a disclosure.

## Login companion

`/login` has welcome → email → password steps, reversible navigation, sanitized
errors and disabled submission during requests. It signs into existing Supabase
teacher accounts. It does not create accounts or assign station permissions.
The animated character is Cues' companion, not the teacher's avatar. It uses the
MIT-licensed `@bible-strong/avatar-react` and `@bible-strong/avatar-core` packages,
with a restrained pointer-following gaze, a resting password state and reduced
motion support. Rendering stays in the browser.

Enable `CUES_FLAG_WEB_TEACHER_LOGIN=1` alongside `CUES_FLAG_WEB_DASHBOARD=1` when
building or running the preview. Both registry defaults remain off. With login off,
`/login` shows an unavailable page and does not load the companion or sign-in code.
Flags are resolved when Next.js prerenders: rebuild a production preview after
changing them. Existing `web.session_controls` permissions and gates still apply.

## Photon

`/settings/notifications` provides a dedicated destination and reports Photon as
coming soon, not connected, with delivery unavailable. Actual routing remains
Michelle's integration work. There are no notification writes or credentials in
this frontend change.

## Verification

- `npm run lint`
- `npm run test` (48 passing at verification time, including the login-off gate)
- `CUES_FLAG_WEB_DASHBOARD=1 CUES_FLAG_WEB_TEACHER_LOGIN=1 npm run build`
- Safari: reference inspection, welcome/email/password navigation, classroom and
  notifications destinations. Used a simulated email; no sign-in request sent.
- Isolated Chrome: desktop (1440) and mobile (390) captures under
  `.impeccable/review/`; production preview on `http://127.0.0.1:3001`.
- Impeccable mechanical scan: no findings on changed UI targets.

Still needed: successful sign-in with an existing authorized test teacher account,
real station session writes under the existing controls flag, and Photon delivery
once its backend integration exists. No student camera frames were used or sent.
