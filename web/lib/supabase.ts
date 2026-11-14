import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Reuse each browser auth mode across React mounts and route changes.
// Server renders must never share an authenticated client between requests.
const browserClients = new Map<boolean, SupabaseClient>();

export function createDashboardClient(persistTeacherSession = false) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Dashboard connection is not configured.");
  if (!key.startsWith("sb_publishable_"))
    throw new Error("Use a Supabase publishable key for the dashboard.");
  const cached =
    typeof window !== "undefined"
      ? browserClients.get(persistTeacherSession)
      : undefined;
  if (cached) return cached;
  const client = createClient(url, key, {
    auth: {
      persistSession: persistTeacherSession,
      autoRefreshToken: persistTeacherSession,
      detectSessionInUrl: false,
      ...(!persistTeacherSession
        ? { storageKey: "cues-readonly-observations" }
        : {}),
    },
  });
  if (typeof window !== "undefined")
    browserClients.set(persistTeacherSession, client);
  return client;
}
