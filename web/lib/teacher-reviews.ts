/** Proposed read projection for Michelle's pending Supabase persistence.
 * Identity/priority come from TeacherReview.evaluation; rationale/evidence from assessment.
 * This is not the legacy alerts table and performs no agent eligibility checks.
 */
import { isInterventionKey, type InterventionKey } from "./interventions.ts";

export type AssessmentDecision =
  "continue_monitoring" | "teacher_review_warranted";
export type ReviewPriority = "normal" | "elevated";
export type EvidenceSource =
  | "current_progress"
  | "activity"
  | "recent_progress_history"
  | "prompt_history";
export type TeacherReview = Readonly<{
  id: string;
  session_id: string;
  seat_id: string;
  activity_id: string;
  created_at: string;
  priority: ReviewPriority;
  decision?: AssessmentDecision | null;
  rationale: string;
  evidence_used: readonly EvidenceSource[];
  /** "expired": closed automatically (its session ended, or the task was completed).
   * "reviewed": the teacher marked the child as reviewed. Neither is a decision on the review. */
  status: "pending" | "confirmed" | "dismissed" | "expired" | "reviewed";
  resolved_at: string | null;
  progress?: { trend: string; stalled_seconds: number } | null;
  escalation_reason?: string | null;
  /** The agent's one suggested support from the approved menu (migration 018), if any. */
  suggested_intervention?: InterventionKey | null;
}>;

export const REVIEW_COLUMNS =
  "id,session_id,seat_id,activity_id,created_at,priority,decision,rationale,evidence_used,status,resolved_at,evaluation";
/** Only with web.interventions: the column exists after migration 018. */
export const REVIEW_COLUMNS_WITH_INTERVENTIONS = `${REVIEW_COLUMNS},suggested_intervention`;
export const evidenceLabels: Record<EvidenceSource, string> = {
  current_progress: "Current task progress",
  activity: "Activity requirements",
  recent_progress_history: "Recent progress history",
  prompt_history: "Previous prompts",
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function text(value: unknown): string {
  if (typeof value !== "string" || !value.trim())
    throw new Error("Invalid review text");
  return value;
}
function timestamp(value: unknown): string {
  const result = text(value);
  if (
    !/(Z|[+-]\d\d:\d\d)$/i.test(result) ||
    !Number.isFinite(Date.parse(result))
  )
    throw new Error("Invalid review time");
  return result;
}
export function parseTeacherReviews(input: unknown): TeacherReview[] {
  if (!Array.isArray(input)) throw new Error("Invalid review response");
  const ids = new Set<string>();
  return input.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error("Invalid review row");
    const row = value as Record<string, unknown>;
    const id = text(row.id);
    const session_id = text(row.session_id);
    if (!uuid.test(id) || !uuid.test(session_id) || ids.has(id))
      throw new Error("Invalid review identity");
    ids.add(id);
    if (row.priority !== "normal" && row.priority !== "elevated")
      throw new Error("Invalid review priority");
    if (
      !["pending", "confirmed", "dismissed", "expired", "reviewed"].includes(
        String(row.status),
      )
    )
      throw new Error("Invalid review status");
    const evidence = row.evidence_used ?? [];
    if (
      !Array.isArray(evidence) ||
      evidence.some(
        (source) =>
          typeof source !== "string" || !Object.hasOwn(evidenceLabels, source),
      )
    )
      throw new Error("Invalid review evidence");
    const evaluation = row.evaluation as Record<string, unknown> | undefined;
    const progress = evaluation?.progress as Record<string, unknown> | undefined;
    const escalation = evaluation?.escalation as Record<string, unknown> | undefined;
    const validProgress = progress && ['improving', 'stalled', 'completed', 'unknown'].includes(String(progress.trend)) &&
      typeof progress.stalled_seconds === 'number' && Number.isFinite(progress.stalled_seconds) && progress.stalled_seconds >= 0;
    return {
      id,
      session_id,
      seat_id: text(row.seat_id),
      activity_id: text(row.activity_id),
      created_at: timestamp(row.created_at),
      priority: row.priority,
      decision:
        row.decision === "continue_monitoring" ||
        row.decision === "teacher_review_warranted"
          ? row.decision
          : null,
      rationale: text(row.rationale),
      evidence_used: [...new Set(evidence)] as EvidenceSource[],
      status: row.status as TeacherReview["status"],
      resolved_at: row.resolved_at == null ? null : timestamp(row.resolved_at),
      ...("suggested_intervention" in row
        ? {
            suggested_intervention: isInterventionKey(row.suggested_intervention)
              ? row.suggested_intervention
              : null,
          }
        : {}),
      ...(row.evaluation == null ? {} : {
        progress: validProgress ? { trend: String(progress.trend), stalled_seconds: progress.stalled_seconds as number } : null,
        escalation_reason: typeof escalation?.reason === 'string' ? escalation.reason : null,
      }),
    };
  });
}
/** Presentation ordering only; backend priority is never recalculated. */
export function pendingReviews(
  reviews: readonly TeacherReview[],
): TeacherReview[] {
  return reviews
    .filter((review) => review.status === "pending")
    .toSorted(
      (a, b) =>
        Number(b.priority === "elevated") - Number(a.priority === "elevated") ||
        Date.parse(a.created_at) - Date.parse(b.created_at) ||
        a.id.localeCompare(b.id),
    );
}

export type ReviewGroup = {
  seat_id: string;
  reviews: TeacherReview[];
  elevated: boolean;
  latest: string;
};
/** One row per person. Keeps the queue order, so each group leads with its
 * most urgent review; priorities are read, never recalculated. */
export function groupReviewsBySeat(
  reviews: readonly TeacherReview[],
): ReviewGroup[] {
  const groups = new Map<string, ReviewGroup>();
  for (const review of reviews) {
    const group = groups.get(review.seat_id);
    if (!group) {
      groups.set(review.seat_id, {
        seat_id: review.seat_id,
        reviews: [review],
        elevated: review.priority === "elevated",
        latest: review.created_at,
      });
      continue;
    }
    group.reviews.push(review);
    group.elevated ||= review.priority === "elevated";
    if (Date.parse(review.created_at) > Date.parse(group.latest))
      group.latest = review.created_at;
  }
  return [...groups.values()];
}

/** Labels only: never recompute an assessment from seat state or expression. */
export const decisionLabels: Record<AssessmentDecision, string> = {
  continue_monitoring: "Continue monitoring",
  teacher_review_warranted: "Teacher check-in recommended",
};
/** The teacher's decision on a pending review, as the UI words it. The stored
 * values stay "confirmed" and "dismissed"; these labels only make their
 * meaning explicit (Cues flags a possible support need, the teacher agrees or
 * disagrees). No diagnosis, and no claim about why a student is stuck. */
export const resolutionLabels: Record<"confirmed" | "dismissed", string> = {
  confirmed: "Approved",
  dismissed: "Not needed",
};
export const reviewPrompt = {
  title: "Student may need support",
  detail:
    "No progress on this task for a while.",
} as const;
export const priorityLabels: Record<ReviewPriority, string> = {
  normal: "Normal priority",
  elevated: "Elevated priority",
};
const contextLabels: Record<string, string> = {
  stalled_progress_with_expression_context: "Repeated stalled progress",
  stalled_progress: "Repeated stalled progress",
  teacher_review_warranted: "Teacher check-in recommended",
  continue_monitoring: "Continue monitoring",
};
export function teacherRationale(rationale: string): string {
  return rationale.replace(
    /\b[a-z]+(?:_[a-z]+)+\b/g,
    (value) => contextLabels[value] ?? "additional review context",
  );
}
export function activityLabel(id: string, name?: string): string {
  if (name) return name;
  return (
    (
      { raise_hand: "Raise hand", thumbs_up: "Thumbs up" } as Record<
        string,
        string
      >
    )[id] ?? "Activity unavailable"
  );
}
