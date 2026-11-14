# cues — agent instructions

This is a [Spectrum](https://photon.codes/docs/spectrum-ts) app, pinned to `spectrum-ts@^12.16.0`. The entry point is `src/index.ts`, which configures the imessage provider(s) and runs the echo loop.

## Working in this project

- Run the app with `npm run start`.
- Add providers by importing them in `src/index.ts` and listing them in the `Spectrum({ providers: [...] })` config.
- Outgoing message content uses the builders documented in the skill (text, attachment, voice, contact, richlink, poll, group, custom).

## Environment

This project reads secrets from `.env` (gitignored). **Do not read, write, or echo `.env`** — it contains credentials.

If startup fails with an authentication error, tell the user to verify their `PROJECT_ID` / `PROJECT_SECRET` at the [Photon dashboard](https://app.photon.codes).

## Spectrum SDK reference

This project includes the `spectrum` skill from [`photon-hq/skills`](https://github.com/photon-hq/skills). Your agent should auto-discover it. If it doesn't, or if you switch agents, install for your agent with:

```sh
npx skills add photon-hq/skills --skill spectrum --agent <your-agent>
```

(Use `--agent '*'` to install for all supported agents.)

## Manual recipient activation

For the hackathon, use the [Photon dashboard](https://app.photon.codes) to add/invite
only recipients who explicitly opted in through Cues. Cues does not automate
project-user provisioning. Website activation permits sending; an accepted test or review send records the
exact current consent attempt registered through the backend-only guarded RPC.
Keep provider restrictions and consented-phone matching intact. Runtime sending
uses SPECTRUM_PROJECT_ID/SPECTRUM_PROJECT_SECRET, not Dashboard OAuth credentials.

## See also

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- [`spectrum-ts` on GitHub](https://github.com/photon-hq/spectrum-ts)
