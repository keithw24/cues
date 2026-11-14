import "server-only";
import { createClient } from "@supabase/supabase-js";
import { parseEnv } from "node:util";
import { readFileSync } from "node:fs";
import path from "node:path";
import { registerDemoNotifications } from "@/lib/photon-registration";

export async function POST(request: Request) {
  // Server-only config: Next does not load the root/nested Python/Photon envs.
  const root = path.resolve(process.cwd(), process.cwd().endsWith(path.sep + "web") ? ".." : ".");
  const config: Record<string, string> = {};
  for (const file of [".env", "cues/.env"]) {
    try { Object.assign(config, parseEnv(readFileSync(path.join(root, file), "utf8"))); }
    catch { /* Missing files may be replaced by deployment environment values. */ }
  }
  for (const [key, value] of Object.entries(process.env)) if (value) config[key] = value;
  const url = config.SUPABASE_URL ?? config.NEXT_PUBLIC_SUPABASE_URL;
  if (!url || !config.SUPABASE_SERVICE_ROLE_KEY)
    return Response.json({error: "Notification backend is not configured."}, {status: 503});
  const admin = createClient(url, config.SUPABASE_SERVICE_ROLE_KEY, {
    auth: {persistSession: false, autoRefreshToken: false},
  });
  return registerDemoNotifications(request, {admin,
    config: {projectId: config.SPECTRUM_PROJECT_ID}});
}
