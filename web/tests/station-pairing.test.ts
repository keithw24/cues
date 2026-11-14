import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import { readStationMemberships, redeemStationCode, StationSignInRequired } from "../lib/station-pairing.ts";

function mock({ signedIn = true, rows = [{station_id: "S1"}], error = null as unknown } = {}) {
  const calls: unknown[] = [];
  const query = {
    select(value: string) { calls.push(value); return query; },
    eq(key: string, value: string) { calls.push([key, value]); return query; },
    abortSignal() { return Promise.resolve({data: rows, error}); },
  };
  const client = {
    auth: {getUser: async () => ({data: {user: signedIn ? {id: "teacher"} : null}, error: null})},
    from(table: string) { calls.push(table); return query; },
    rpc(name: string, args: unknown) { calls.push([name, args]); return query; },
  } as unknown as SupabaseClient;
  return {client, calls};
}
test("membership reads use only the authenticated teacher and preserve existing stations", async () => {
  const value = mock();
  assert.deepEqual(await readStationMemberships(value.client), ["S1"]);
  assert.deepEqual(value.calls, ["station_teachers", "station_id", ["teacher_id", "teacher"]]);
});
test("empty memberships are a valid connected-account state", async () => {
  assert.deepEqual(await readStationMemberships(mock({rows: []}).client), []);
});
test("redemption sends only the code and returns S1", async () => {
  const value = mock();
  assert.equal(await redeemStationCode(value.client, " ABCD-1234 "), "S1");
  assert.deepEqual(value.calls, [["redeem_station_pairing_code", {code: "ABCD-1234"}]]);
});
test("invalid expired or used codes show a generic error", async () => {
  await assert.rejects(redeemStationCode(mock({error: {code: "22023", message: "private"}}).client, "bad"), /That pairing code is invalid or no longer available/);
});
test("network/provider details are never shown", async () => {
  await assert.rejects(redeemStationCode(mock({error: {message: "secret"}}).client, "code"), /Check your connection/);
});
test("signed-out callers cannot read memberships or redeem codes", async () => {
  const value = mock({signedIn: false});
  await assert.rejects(readStationMemberships(value.client), StationSignInRequired);
  await assert.rejects(redeemStationCode(value.client, "code"), StationSignInRequired);
  assert.deepEqual(value.calls, []);
});
test("form source exposes controls, loading protection and existing memberships", () => {
  // Source contract only; the repo's Node test runner does not mount React components.
  const source = readFileSync(new URL("../components/station-pairing-form.tsx", import.meta.url), "utf8");
  for (const label of ["Pairing code", "Connect station", "Connected stations", "Connected to", "Back to classroom"])
    assert.ok(source.includes(label));
  assert.match(source, /disabled=\{state === "saving" \|\| !code.trim\(\)\}/);
  assert.ok(source.includes('locked.current = true'));
});
