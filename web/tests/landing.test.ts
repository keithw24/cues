import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { isEnabled } from "../lib/flags.ts";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("landing defaults off and the server override turns it on", () => {
  assert.equal(isEnabled("web.landing", {}), false);
  assert.equal(isEnabled("web.landing", { CUES_FLAG_WEB_LANDING: "1" }), true);
});

test("with landing off, / still renders the dashboard", () => {
  const home = read("../app/page.tsx");
  assert.match(home, /if \(!isEnabled\("web\.landing"\)\) return DashboardPage\(\);/);
  assert.match(read("../app/dashboard/page.tsx"), /isEnabled\("web\.dashboard"\)/);
});

test("sign-up defaults off and shows an unavailable page without the flag", () => {
  assert.equal(isEnabled("web.teacher_signup", {}), false);
  const page = read("../app/signup/page.tsx");
  assert.match(page, /if \(!isEnabled\("web\.teacher_signup"\)\)/);
  assert.match(page, /Teacher sign-up is unavailable\./);
  // With sign-up off, the landing page sends teachers to sign in instead.
  assert.match(
    read("../components/landing.tsx"),
    /isEnabled\("web\.teacher_signup"\) \? "\/signup" : "\/login"/,
  );
});
