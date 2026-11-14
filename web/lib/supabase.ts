import { createClient } from "@supabase/supabase-js";

export function createDashboardClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Dashboard connection is not configured.");
  if (!key.startsWith("sb_publishable_"))
    throw new Error("Use a Supabase publishable key for the dashboard.");
  return createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  });
}
