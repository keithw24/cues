import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import { registerDemoNotifications } from "../lib/photon-registration.ts";

function harness(status = "registering", signedIn = true) {
  const calls: unknown[] = [];
  const admin = {
    auth: {getUser: async () => ({error: null, data: {user: signedIn ? {
      id: "teacher", email: "teacher@example.com", email_confirmed_at: "verified",
    } : null}})},
    rpc: async (name: string, args: unknown) => {
      calls.push({name, args});
      return {data: [{user_id: "teacher", notification_phone: "+12025550101",
        photon_registration_status: status}], error: null};
    },
  } as unknown as SupabaseClient;
  const invoke = (body: unknown) => registerDemoNotifications(new Request("http://localhost/api/notifications/register", {
    method: "POST", headers: {Authorization: "Bearer supabase-session"}, body: JSON.stringify(body),
  }), {admin, config: {projectId: "project"}});
  return {invoke, calls};
}
const consent = {opt_in: true, first_name: "Ada", last_name: "Lovelace"};
test("explicit opt-in queues activation using the verified user's profile", async () => {
  const value = harness(); const response = await value.invoke(consent);
  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), {status: "pending", notification_opt_in: true,
    message: "Notifications: activating"});
  assert.deepEqual(value.calls, [{name: "prepare_teacher_notification_registration", args: {
    p_user_id: "teacher", p_opt_in: true, p_first_name: "Ada", p_last_name: "Lovelace", p_project_id: "project",
  }}]);
});
test("missing consent, arbitrary identities and signed-out users cannot queue activation", async () => {
  assert.equal((await harness().invoke({})).status, 400);
  assert.equal((await harness().invoke({...consent, user_id: "another"})).status, 400);
  assert.equal((await harness().invoke({...consent, phone_number: "+12025550999"})).status, 400);
  assert.equal((await harness("registering", false).invoke(consent)).status, 401);
});
test("registered state is read from the trusted RPC; browser cannot mark itself registered", async () => {
  assert.equal((await harness().invoke({...consent, status: "registered"})).status, 400);
  const response = await harness("registered").invoke(consent);
  assert.equal((await response.json()).status, "registered");
});
test("explicit revocation remains available", async () => {
  const response = await harness().invoke({opt_in: false});
  assert.deepEqual(await response.json(), {status: "unregistered", notification_opt_in: false});
});
