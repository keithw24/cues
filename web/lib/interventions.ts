import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * The approved intervention menu (PRD 12, 13). The agent may suggest one of these on a review
 * and nothing else; the teacher approves it, or picks another, before anything is recorded.
 * Cues changes no task or instruction by itself: the approval is the teacher's record.
 * Same keys as shared/contracts.py INTERVENTION_MENU and migration 20261114001800.
 */
export const INTERVENTION_MENU = {
  repeat_instruction: "Repeat the instruction",
  show_example: "Show an example",
  model_task: "Model the task",
  smaller_steps: "Break it into smaller steps",
  offer_break: "Offer a short break",
  adult_check_in: "Check in with the student",
} as const;

export type InterventionKey = keyof typeof INTERVENTION_MENU;

export function isInterventionKey(value: unknown): value is InterventionKey {
  return typeof value === "string" && Object.hasOwn(INTERVENTION_MENU, value);
}

/** Approve a support for a review the signed-in teacher owns. A pending review is also
 * confirmed ("Support needed") in the same step. Returns the approved key. */
export async function approveIntervention(
  client: SupabaseClient,
  reviewId: string,
  action: InterventionKey,
): Promise<InterventionKey> {
  if (!isInterventionKey(action)) throw new Error("Choose a support from the list.");
  try {
    const { data, error } = await client
      .rpc("approve_review_intervention", { review_id: reviewId, action })
      .abortSignal(AbortSignal.timeout(12000));
    if (error) throw error;
    const row = data as { review_id?: unknown; action?: unknown } | null;
    if (!row || row.review_id !== reviewId || row.action !== action)
      throw new Error("Unconfirmed approval");
    return action;
  } catch {
    throw new Error(
      "Could not save that support. Refresh the queue to check the review before trying again.",
    );
  }
}
