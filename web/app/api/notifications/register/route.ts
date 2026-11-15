import "server-only";
import { createClient } from "@supabase/supabase-js";
import { notificationServerConfig } from "@/lib/notification-server-config";
import { registerDemoNotifications } from "@/lib/photon-registration";

export async function POST(request: Request) {
  const config = notificationServerConfig();
  const url = config.SUPABASE_URL ?? config.NEXT_PUBLIC_SUPABASE_URL;
  if (!url || !config.SUPABASE_SERVICE_ROLE_KEY)
    return Response.json({error: "Notification backend is not configured."}, {status: 503});
  const admin = createClient(url, config.SUPABASE_SERVICE_ROLE_KEY, {
    auth: {persistSession: false, autoRefreshToken: false},
  });
  return registerDemoNotifications(request, {admin,
    config: {projectId: config.SPECTRUM_PROJECT_ID}});
}
