# Photon / Spectrum package (`cues/`)

This nested package supplies the on-demand iMessage sender used after a new
teacher review persists. It does not need a long-running process in the Cues demo.

Installing `web/` (`npm ci`) also installs `cues/` through a postinstall step, so CI and Vercel get `spectrum-ts` for the hosted test send. Configure backend-only `SPECTRUM_PROJECT_ID`,
`SPECTRUM_PROJECT_SECRET`, `SPECTRUM_TEACHER_PHONE`, and optional
`SPECTRUM_SENDER_PHONE` in `cues/.env` (git-ignored). The opted-in destination
must be active in Spectrum Users. `cues/src/notify.ts` loads this file relative to its
module and sends minimal teacher-facing text; no secrets/phones are logged.

The separate `npm start` / `npm run dev` commands run the scaffold echo listener
in src/index.ts, not the review notification worker. See [startup](../STARTUP.md)
for the normal stack command and [agent notes](michelle.md) for verified
notification behavior and failure handling.
