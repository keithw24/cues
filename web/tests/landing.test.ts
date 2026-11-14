import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { isEnabled } from "../lib/flags.ts";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("landing defaults on and the server override turns it off", () => {
  assert.equal(isEnabled("web.landing", {}), true);
  assert.equal(isEnabled("web.landing", { CUES_FLAG_WEB_LANDING: "0" }), false);
});

test("with landing off, / still renders the dashboard", () => {
  const home = read("../app/page.tsx");
  assert.match(home, /if \(!isEnabled\("web\.landing"\)\) return DashboardPage\(\);/);
  assert.match(read("../app/dashboard/page.tsx"), /isEnabled\("web\.dashboard"\)/);
});

test("sign-up defaults on and shows an unavailable page when turned off", () => {
  assert.equal(isEnabled("web.teacher_signup", {}), true);
  assert.equal(
    isEnabled("web.teacher_signup", { CUES_FLAG_WEB_TEACHER_SIGNUP: "0" }),
    false,
  );
  const page = read("../app/signup/page.tsx");
  assert.match(page, /if \(!isEnabled\("web\.teacher_signup"\)\)/);
  assert.match(page, /Teacher sign-up is unavailable\./);
  // With sign-up off, the landing page sends teachers to sign in instead.
  assert.match(
    read("../components/landing.tsx"),
    /isEnabled\("web\.teacher_signup"\) \? "\/signup" : "\/login"/,
  );
});

test("the email-confirmed page is unavailable when sign-up is off", () => {
  const page = read("../app/auth/confirmed/page.tsx");
  assert.match(page, /if \(!isEnabled\("web\.teacher_signup"\)\)/);
  assert.match(page, /Teacher sign-up is unavailable\./);
});
