import type { SupabaseClient } from "@supabase/supabase-js";

export type NotificationSettings = {
  notification_opt_in: boolean;
  notification_phone: string | null;
  photon_registration_status: "unregistered" | "registering" | "registered" | "failed";
  first_name: string | null;
  last_name: string | null;
};
export type NotificationState = "not enabled" | "activating" | "enabled" | "activation failed";
export class NotificationSignInRequired extends Error {
  constructor() { super("Sign in to manage demo notifications."); }
}
export async function sendTestNotification(client: SupabaseClient, fetcher: typeof fetch = fetch) {
  const {data, error} = await client.auth.getSession();
  if (error || !data.session?.access_token) throw new NotificationSignInRequired();
  const response = await fetcher("/api/notifications/test", {method: "POST",
    headers: {Authorization: `Bearer ${data.session.access_token}`}, signal: AbortSignal.timeout(40000)});
  if (response.status === 401) throw new NotificationSignInRequired();
  const result = await response.json();
  if (!response.ok || !["registered", "pending"].includes(result.status))
    throw new Error("Notification test failed. Please retry.");
  return result.status as "registered" | "pending";
}
export function notificationState(settings: NotificationSettings | null, phone: string | null,
  phoneDirty = false): NotificationState {
  if (phoneDirty || !phone || !settings?.notification_opt_in || settings.notification_phone !== phone)
    return "not enabled";
  if (settings.photon_registration_status === "registered") return "enabled";
  if (settings.photon_registration_status === "registering") return "activating";
  if (settings.photon_registration_status === "failed") return "activation failed";
  return "not enabled";
}
export async function readNotificationSettings(client: SupabaseClient) {
  try {
    const {data, error} = await client.auth.getUser();
    if (error || !data.user) throw new NotificationSignInRequired();
    const [settings, profile] = await Promise.all([
      client.from("teacher_notification_settings")
        .select("notification_opt_in,notification_phone,photon_registration_status,first_name,last_name")
        .eq("user_id", data.user.id).maybeSingle(),
      client.from("teacher_profiles").select("phone_number").eq("user_id", data.user.id).maybeSingle(),
    ]);
    if (settings.error || profile.error) throw new Error();
    const row = settings.data;
    if (row && (typeof row.notification_opt_in !== "boolean" ||
      !["unregistered", "registering", "registered", "failed"].includes(row.photon_registration_status) ||
      (row.notification_phone !== null && typeof row.notification_phone !== "string"))) throw new Error();
    return {settings: row as NotificationSettings | null, phone: profile.data?.phone_number ?? null};
  } catch (error) {
    if (error instanceof NotificationSignInRequired) throw error;
    throw new Error("Notification status could not be loaded. Try again.");
  }
}
export async function requestDemoNotifications(client: SupabaseClient, input: {
  opt_in: boolean; first_name?: string; last_name?: string;
}, fetcher: typeof fetch = fetch): Promise<"pending" | "registered" | "unregistered"> {
  if (input.opt_in && (!input.first_name?.trim() || !input.last_name?.trim()))
    throw new Error("Enter your first and last name and confirm opt-in.");
  try {
    const {data, error} = await client.auth.getSession();
    if (error || !data.session?.access_token) throw new NotificationSignInRequired();
    const body = input.opt_in ? {opt_in: true, first_name: input.first_name!.trim(), last_name: input.last_name!.trim()} : {opt_in: false};
    const response = await fetcher("/api/notifications/register", {
      method: "POST", headers: {Authorization: `Bearer ${data.session.access_token}`, "Content-Type": "application/json"},
      body: JSON.stringify(body), signal: AbortSignal.timeout(15000),
    });
    if (response.status === 401) throw new NotificationSignInRequired();
    const result = await response.json();
    if (!response.ok || !["pending", "registered", "unregistered"].includes(result.status)) throw new Error();
    return result.status;
  } catch (error) {
    if (error instanceof NotificationSignInRequired) throw error;
    throw new Error("Notification settings could not be saved. Check your saved phone and try again.");
  }
}
