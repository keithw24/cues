import type {SupabaseClient} from "@supabase/supabase-js";
import {sendSpectrumMessage, SpectrumSendError, type SpectrumSendConfig} from "cues/send";
import { E164 } from "./ids.ts";

type Sender = typeof sendSpectrumMessage;
/** Verified user ID comes from the endpoint; all destination facts come from Supabase. */
export async function sendOwnTestNotification(admin: SupabaseClient, config: SpectrumSendConfig,
  userId: string, sender: Sender = sendSpectrumMessage): Promise<{status: "registered" | "pending"}> {
  if (!config.projectId || !config.projectSecret) throw new Error("Notifications are not configured.");
  const [profile, settings] = await Promise.all([
    admin.from("teacher_profiles").select("phone_number").eq("user_id", userId).maybeSingle(),
    admin.from("teacher_notification_settings")
      .select("notification_opt_in,notification_phone,photon_project_id,registration_attempt")
      .eq("user_id", userId).maybeSingle(),
  ]);
  const phone = profile.data?.phone_number;
  const state = settings.data;
  if (profile.error || settings.error || !state || state.notification_opt_in !== true ||
      typeof phone !== "string" || !E164.test(phone) ||
      state.notification_phone !== phone || state.photon_project_id !== config.projectId ||
      !state.registration_attempt) throw new Error("Current notification consent is required.");
  // Registration status is intentionally not a pre-send gate.
  let outcome: "accepted" | "target_not_allowed" | "provider_failure" | "network_failure" = "accepted";
  try { await sender(config, phone, "Cues notifications are connected."); }
  catch (error) { outcome = error instanceof SpectrumSendError ? error.category : "provider_failure"; }
  const recorded = await admin.rpc("record_teacher_notification_send", {
    p_user_id: userId, p_phone: phone, p_attempt: state.registration_attempt,
    p_project_id: config.projectId, p_result: outcome,
  });
  if (recorded.error || recorded.data !== true)
    throw new Error("Consent changed or send acknowledgement could not be recorded.");
  if (outcome === "accepted") return {status: "registered"};
  if (outcome === "target_not_allowed") return {status: "pending"};
  throw new Error("Notification provider unavailable.");
}
