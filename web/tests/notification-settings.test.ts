import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import type { SupabaseClient } from "@supabase/supabase-js";
import { notificationState, requestDemoNotifications, readNotificationSettings,
  NotificationSignInRequired, type NotificationSettings } from "../lib/notification-settings.ts";

const phone = "+12025550101";
const settings: NotificationSettings = {notification_opt_in: true, notification_phone: phone,
  photon_registration_status: "registered", first_name: "Ada", last_name: "Lovelace"};
const client = {auth: {getSession: async () => ({data: {session: {access_token: "user-session"}}, error: null})}} as unknown as SupabaseClient;
test("status requires consent for the exact current saved phone", () => {
  assert.equal(notificationState(null, phone), "not enabled");
  assert.equal(notificationState(settings, phone), "enabled");
  assert.equal(notificationState({...settings, notification_opt_in: false}, phone), "not enabled");
  assert.equal(notificationState(settings, "+12025550102"), "not enabled");
  assert.equal(notificationState(settings, phone, true), "not enabled");
  assert.equal(notificationState({...settings, photon_registration_status: "registering"}, phone), "activating");
  assert.equal(notificationState({...settings, photon_registration_status: "failed"}, phone), "activation failed");
});
test("enable sends only explicit consent and names; 202 is activation pending", async () => {
  let body: unknown;
  const fetcher = (async (url, init) => {
    assert.equal(url, "/api/notifications/register");
    body = JSON.parse(init!.body as string);
    assert.equal((init!.headers as Record<string,string>).Authorization, "Bearer user-session");
    return Response.json({status: "pending"}, {status: 202});
  }) as typeof fetch;
  assert.equal(await requestDemoNotifications(client, {opt_in: true, first_name: " Ada ", last_name: " Lovelace ",
    ...({user_id: "other", phone_number: phone, email: "other@example.com"} as object)}, fetcher), "pending");
  assert.deepEqual(body, {opt_in: true, first_name: "Ada", last_name: "Lovelace"});
});
test("disable sends only opt_in false", async () => {
  const fetcher = (async (_url, init) => {
    assert.deepEqual(JSON.parse(init!.body as string), {opt_in: false});
    return Response.json({status: "unregistered"});
  }) as typeof fetch;
  assert.equal(await requestDemoNotifications(client, {opt_in: false}, fetcher), "unregistered");
});
test("auth and provider errors remain safe", async () => {
  const signedOut = {auth: {getSession: async () => ({data: {session: null}, error: null})}} as unknown as SupabaseClient;
  await assert.rejects(requestDemoNotifications(signedOut, {opt_in: false}), NotificationSignInRequired);
  await assert.rejects(requestDemoNotifications(client, {opt_in: true}), /first and last/);
  const fetcher = (async () => Response.json({error: "private provider details"}, {status: 502})) as typeof fetch;
  await assert.rejects(requestDemoNotifications(client, {opt_in: false}, fetcher), /settings could not be saved/);
});
test("membership-free status read is scoped to Auth user and reads the authoritative phone", async () => {
  const calls: unknown[] = [];
  const mock = {auth: {getUser: async () => ({data: {user: {id: "teacher"}}, error: null})},
    from(table: string) {return {
      select(fields: string) {calls.push([table, fields]); return this;},
      eq(key: string, value: string) {calls.push([key, value]); return this;},
      maybeSingle: async () => ({data: table === "teacher_profiles" ? {phone_number: phone} : settings, error: null}),
    };},
  } as unknown as SupabaseClient;
  const result = await readNotificationSettings(mock);
  assert.equal(result.phone, phone);
  assert.equal(notificationState(result.settings, result.phone), "enabled");
  assert.equal(calls.filter(value => JSON.stringify(value) === '["user_id","teacher"]').length, 2);
});
test("notification section source includes names, explicit checkbox, safe statuses and disable control", () => {
  const source = readFileSync(new URL("../components/demo-notifications.tsx", import.meta.url), "utf8");
  for (const label of ["demo notifications", "First name", "Last name", "I want to receive Cues demo notifications",
    "Enable notifications", "Disable notifications", "Notifications are being activated for this phone.",
    "Notifications enabled", "Notifications could not be activated yet."])
    assert.ok(source.includes(label));
  assert.ok(source.includes('!consentValid'));
  assert.ok(source.includes('locked.current = true'));
  assert.ok(source.includes('consentPhone === phone'));
});
