import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import type {SupabaseClient} from "@supabase/supabase-js";
import {testDemoNotification} from "../lib/notification-test.ts";
import {sendTestNotification} from "../lib/notification-settings.ts";

const admin = {auth: {getUser: async () => ({data: {user: {id: "authenticated-owner"}}})}} as unknown as SupabaseClient;
test("test send targets only verified identity and returns pending or enabled", async () => {
  for (const status of ["pending", "registered"]) {
    const response = await testDemoNotification(new Request("http://local", {
      method: "POST", headers: {authorization: "Bearer token"}}), admin, async id => {
      assert.equal(id, "authenticated-owner"); return {status};
    });
    assert.equal(response.status, status === "pending" ? 202 : 200);
    assert.deepEqual(await response.json(), {status});
  }
});
test("identity overrides and unauthenticated tests rejected without sending", async () => {
  const send = async () => {assert.fail("must not send");};
  assert.equal((await testDemoNotification(new Request("http://local", {method: "POST"}), admin, send)).status, 401);
  assert.equal((await testDemoNotification(new Request("http://local", {method: "POST",
    headers: {authorization: "Bearer token"}, body: JSON.stringify({phone: "other"})}), admin, send)).status, 400);
});
test("browser sends no identity or destination in test request", async () => {
  const client = {auth: {getSession: async () => ({data: {session: {access_token: "token"}}})}} as unknown as SupabaseClient;
  assert.equal(await sendTestNotification(client, async (url, init) => {
    assert.equal(url, "/api/notifications/test"); assert.equal(init?.body, undefined);
    return Response.json({status: "registered"});
  }), "registered");
});
test("provider details are not exposed and UI gates test sends on current consent", async () => {
  const response = await testDemoNotification(new Request("http://local", {method: "POST",
    headers: {authorization: "Bearer token"}}), admin, async () => {
    throw new Error("private provider error");
  });
  assert.equal(response.status, 503);
  assert.doesNotMatch(await response.text(), /private provider/);
  const source = readFileSync(new URL("../components/demo-notifications.tsx", import.meta.url), "utf8");
  assert.match(source, /Send test notification/);
  assert.match(source, /notification_phone === phone/);
  assert.match(source, /phone === authoritativePhone/);
  assert.match(source, /disabled=\{loading \|\| saving \|\| profileSaving\}/);
});
