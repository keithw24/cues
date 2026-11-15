import "server-only";
import {createClient} from "@supabase/supabase-js";
import {testDemoNotification} from "@/lib/notification-test";
import {sendOwnTestNotification} from "@/lib/notification-send";
import {notificationServerConfig} from "@/lib/notification-server-config";

export const runtime = "nodejs";
export const maxDuration = 40;
export async function POST(request: Request) {
  const config = notificationServerConfig();
  const url = config.SUPABASE_URL ?? config.NEXT_PUBLIC_SUPABASE_URL;
  if (!url || !config.SUPABASE_SERVICE_ROLE_KEY ||
      !config.SPECTRUM_PROJECT_ID || !config.SPECTRUM_PROJECT_SECRET)
    return Response.json({error: "Notifications are not configured."}, {status: 503});
  const admin = createClient(url, config.SUPABASE_SERVICE_ROLE_KEY,
    {auth: {persistSession: false, autoRefreshToken: false}});
  return testDemoNotification(request, admin, userId => sendOwnTestNotification(admin, {
    projectId: config.SPECTRUM_PROJECT_ID, projectSecret: config.SPECTRUM_PROJECT_SECRET,
    senderPhone: config.SPECTRUM_SENDER_PHONE,
  }, userId));
}
