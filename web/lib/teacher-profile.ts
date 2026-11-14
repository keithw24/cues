import type { SupabaseClient } from "@supabase/supabase-js";

/** public.teacher_profiles (migration 006). Supabase Auth stays the source of truth for email. */
export type TeacherProfile = {
  user_id: string;
  display_name: string | null;
  phone_number: string | null;
};
export type ProfileInput = {
  display_name: string | null;
  phone_number: string | null;
};

const COLUMNS = "user_id,display_name,phone_number";
const E164 = /^\+[1-9][0-9]{7,14}$/;
const MAX_NAME = 80;

export function cleanProfileInput(input: ProfileInput): ProfileInput {
  const name = input.display_name?.trim() || null;
  if (name && name.length > MAX_NAME)
    throw new Error(`Use ${MAX_NAME} characters or fewer for your name.`);
  const phone = input.phone_number?.trim() || null;
  if (phone && !E164.test(phone))
    throw new Error("Enter a mobile number with its country code.");
  return { display_name: name, phone_number: phone };
}

function parseProfile(row: unknown, userId: string): TeacherProfile {
  const r = row as TeacherProfile;
  if (
    !r ||
    typeof r !== "object" ||
    r.user_id !== userId ||
    (r.display_name !== null && typeof r.display_name !== "string") ||
    (r.phone_number !== null &&
      (typeof r.phone_number !== "string" || !E164.test(r.phone_number)))
  )
    throw new Error("Invalid profile response");
  return {
    user_id: r.user_id,
    display_name: r.display_name,
    phone_number: r.phone_number,
  };
}

/** The verified Auth user; profile rows are keyed only by this ID. */
async function authUser(client: SupabaseClient) {
  const { data, error } = await client.auth.getUser();
  if (error || !data.user) throw new Error("Sign in to manage your profile.");
  return data.user;
}

export async function readTeacherProfile(
  client: SupabaseClient,
): Promise<TeacherProfile | null> {
  const user = await authUser(client);
  const { data, error } = await client
    .from("teacher_profiles")
    .select(COLUMNS)
    .eq("user_id", user.id)
    .maybeSingle();
  if (error) throw new Error("Your profile could not be loaded.");
  return data === null ? null : parseProfile(data, user.id);
}

export async function saveTeacherProfile(
  client: SupabaseClient,
  input: ProfileInput,
): Promise<TeacherProfile> {
  const user = await authUser(client);
  const { data, error } = await client
    .from("teacher_profiles")
    .upsert(
      { user_id: user.id, ...cleanProfileInput(input) },
      {
        onConflict: "user_id",
      },
    )
    .select(COLUMNS)
    .single();
  if (error) throw new Error("Your profile could not be saved. Try again.");
  return parseProfile(data, user.id);
}

/**
 * Sign-up can't write the profile before the email is confirmed, so it leaves the
 * number in Auth metadata. After the first sign-in, move it into teacher_profiles
 * and clear the metadata copy so only one phone number exists.
 */
export async function syncSignupProfile(client: SupabaseClient) {
  const user = await authUser(client);
  const pending = user.user_metadata?.alert_phone;
  const phone =
    typeof pending === "string" && E164.test(pending) ? pending : null;
  let profile = await readTeacherProfile(client);
  // A number the teacher saved in their profile is never overwritten.
  if (!profile || (!profile.phone_number && phone))
    profile = await saveTeacherProfile(client, {
      display_name: profile?.display_name ?? null,
      phone_number: profile?.phone_number ?? phone,
    });
  if (pending != null) {
    const { error } = await client.auth.updateUser({
      data: { alert_phone: null },
    });
    if (error) throw new Error("Your sign-up number could not be cleared.");
  }
  return profile;
}
