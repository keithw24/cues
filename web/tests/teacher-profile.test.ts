import assert from "node:assert/strict";
import test from "node:test";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  cleanProfileInput,
  saveTeacherProfile,
  syncSignupProfile,
} from "../lib/teacher-profile.ts";
import { isEnabled } from "../lib/flags.ts";

const userId = "44444444-4444-4444-8444-444444444444";

function mock({
  metadata = {} as Record<string, unknown>,
  row = null as Record<string, unknown> | null,
  signedIn = true,
} = {}) {
  const upserts: unknown[] = [];
  const metadataUpdates: unknown[] = [];
  const query = {
    select: () => query,
    eq: () => query,
    maybeSingle: async () => ({ data: row, error: null }),
    single: async () => ({ data: row, error: null }),
    upsert(value: Record<string, unknown>) {
      upserts.push(value);
      row = { display_name: null, phone_number: null, ...value };
      return query;
    },
  };
  const client = {
    auth: {
      getUser: async () => ({
        data: {
          user: signedIn ? { id: userId, user_metadata: metadata } : null,
        },
        error: null,
      }),
      updateUser: async (value: unknown) => {
        metadataUpdates.push(value);
        return { error: null };
      },
    },
    from: (table: string) => {
      assert.equal(table, "teacher_profiles");
      return query;
    },
  } as unknown as SupabaseClient;
  return { client, upserts, metadataUpdates };
}

test("teacher profile is off by default", () => {
  assert.equal(isEnabled("web.teacher_profile", {}), false);
});

test("profile input keeps E.164 numbers and rejects others", () => {
  assert.deepEqual(
    cleanProfileInput({
      display_name: "  Ms. R ",
      phone_number: "+16095551234",
    }),
    { display_name: "Ms. R", phone_number: "+16095551234" },
  );
  assert.deepEqual(cleanProfileInput({ display_name: " ", phone_number: "" }), {
    display_name: null,
    phone_number: null,
  });
  assert.throws(() =>
    cleanProfileInput({ display_name: null, phone_number: "609-555-1234" }),
  );
});

test("save keys the row by the authenticated user, never by input", async () => {
  const { client, upserts } = mock();
  const saved = await saveTeacherProfile(client, {
    display_name: "Ms. R",
    phone_number: "+16095551234",
    // A caller-supplied ID must be ignored.
    ...({ user_id: "55555555-5555-4555-8555-555555555555" } as object),
  });
  assert.deepEqual(upserts, [
    { user_id: userId, display_name: "Ms. R", phone_number: "+16095551234" },
  ]);
  assert.equal(saved.user_id, userId);
});

test("save requires a signed-in teacher", async () => {
  await assert.rejects(
    saveTeacherProfile(mock({ signedIn: false }).client, {
      display_name: null,
      phone_number: null,
    }),
  );
});

test("first sign-in moves the sign-up number into the profile", async () => {
  const { client, upserts, metadataUpdates } = mock({
    metadata: { alert_phone: "+16095551234" },
  });
  const profile = await syncSignupProfile(client);
  assert.equal(profile.phone_number, "+16095551234");
  assert.equal(upserts.length, 1);
  assert.deepEqual(metadataUpdates, [{ data: { alert_phone: null } }]);
});

test("a saved profile number is never overwritten by sign-up metadata", async () => {
  const { client, upserts, metadataUpdates } = mock({
    metadata: { alert_phone: "+16095550000" },
    row: {
      user_id: userId,
      display_name: "Ms. R",
      phone_number: "+16095551234",
    },
  });
  const profile = await syncSignupProfile(client);
  assert.equal(profile.phone_number, "+16095551234");
  assert.equal(upserts.length, 0);
  assert.equal(metadataUpdates.length, 1);
});
