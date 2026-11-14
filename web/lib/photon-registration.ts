/** Server endpoint logic. Never import into a Client Component. */
import type { SupabaseClient } from "@supabase/supabase-js";

type Config = { projectId?: string };
type Dependencies = { admin: SupabaseClient; config: Config };
const reply = (body: object, status = 200) => Response.json(body, {
  status, headers: { "Cache-Control": "no-store" },
});
const E164 = /^\+[1-9]\d{7,14}$/;
const object = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};

export async function registerDemoNotifications(request: Request, {admin, config}: Dependencies) {
  const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/i)?.[1];
  if (!token) return reply({error: "Sign in to manage notifications."}, 401);
  let user;
  try {
    const auth = await admin.auth.getUser(token);
    if (auth.error || !auth.data.user) return reply({error: "Sign in to manage notifications."}, 401);
    user = auth.data.user;
  } catch { return reply({error: "Could not verify sign-in."}, 503); }
  if (!user.email || !user.email_confirmed_at)
    return reply({error: "Confirm your email before enabling notifications."}, 403);
  let body: Record<string, unknown>;
  try { body = object(await request.json()); }
  catch { return reply({error: "Invalid notification request."}, 400); }
  if (typeof body.opt_in !== "boolean" || Object.keys(body).some(key =>
    !["opt_in", "first_name", "last_name"].includes(key)))
    return reply({error: "Provide explicit notification consent and your own names only."}, 400);
  const first = typeof body.first_name === "string" ? body.first_name.trim() : "";
  const last = typeof body.last_name === "string" ? body.last_name.trim() : "";
  if (body.opt_in && (!first || !last || first.length > 80 || last.length > 80))
    return reply({error: "Enter your first and last name explicitly."}, 400);
  if (body.opt_in && !config.projectId) return reply({error: "Notifications are not configured."}, 503);
  let settings;
  try {
    const prepared = await admin.rpc("prepare_teacher_notification_registration", {
      p_user_id: user.id, p_opt_in: body.opt_in,
      p_first_name: first, p_last_name: last, p_project_id: config.projectId ?? "",
    });
    if (prepared.error) {
      if (prepared.error.code === "55P03") return reply({status: "pending", message: "Notifications: activating"}, 202);
      if (prepared.error.code === "22023") return reply({error: "Save a valid profile phone before enabling notifications."}, 400);
      throw new Error();
    }
    settings = prepared.data?.[0];
    if (!settings || settings.user_id !== user.id) throw new Error();
  } catch { return reply({error: "Could not save notification settings."}, 503); }
  if (!body.opt_in) return reply({status: "unregistered", notification_opt_in: false});
  if (!E164.test(settings.notification_phone ?? "")) return reply({error: "Save a valid profile phone."}, 400);
  if (settings.photon_registration_status === "registered")
    return reply({status: "registered", notification_opt_in: true});

  // The deployed preparation RPC stores "registering": it now represents a
  // pending manual website activation request. An accepted test/review send
  // records registration automatically against the exact current consent attempt.
  return reply({status: "pending", notification_opt_in: true,
    message: "Notifications: activating"}, 202);
}
