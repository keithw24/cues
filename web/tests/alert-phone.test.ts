import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { normalizeAlertPhone } from "../lib/alert-phone.ts";
import { isEnabled } from "../lib/flags.ts";

test("alert phone numbers combine the country code into E.164", () => {
  assert.equal(normalizeAlertPhone("1", "(555) 123-4567"), "+15551234567");
  assert.equal(normalizeAlertPhone("1", "1 555 123 4567"), "+15551234567");
  assert.equal(normalizeAlertPhone("44", "07946 095 800"), "+447946095800");
  assert.equal(normalizeAlertPhone("61", "412 345 678"), "+61412345678");
  // US and Canada numbers need all ten digits.
  assert.equal(normalizeAlertPhone("1", "555-1234"), null);
  assert.equal(normalizeAlertPhone("1", ""), null);
  assert.equal(normalizeAlertPhone("", "5551234567"), null);
  assert.equal(normalizeAlertPhone("44", "1234567890123456"), null);
});

test("the phone step is off by default and sign-up works without it", () => {
  assert.equal(isEnabled("web.alert_phone", {}), false);
  const page = readFileSync(
    new URL("../app/signup/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /phoneEnabled=\{isEnabled\("web\.alert_phone"\)\}/);
  const login = readFileSync(
    new URL("../components/teacher-login.tsx", import.meta.url),
    "utf8",
  );
  // Without the flag, email goes straight to the password step.
  assert.match(login, /setStep\(askPhone \? "phone" : "password"\)/);
  // With it, the number is required: there is no way past the step without one.
  assert.doesNotMatch(login, /Skip for now/);
});
