import type { SupabaseClient } from "@supabase/supabase-js";
import { evidenceLabels, type EvidenceSource } from "./teacher-reviews.ts";
import { isInterventionKey, type InterventionKey } from "./interventions.ts";

/**
 * Long-term classroom insights: what happened across a teacher's sessions and why Cues asked.
 * Counts for the classroom, never per child and never a score. The shape is
 * InsightsSummary in shared/contracts.py (a contract test keeps them equal); the database
 * function teacher_insights builds it from session_summaries in one request.
 */
export type Insights = {
  range: { from: string; to: string };
  totals: {
    sessions: number;
    class_seconds: number;
    reviews_raised: number;
    confirmed: number;
    dismissed: number;
    reviewed: number;
    expired: number;
    pending: number;
    approved_supports: number;
    median_decision_seconds: number | null;
  };
  previous: { sessions: number; reviews_raised: number };
  weekly: { week_start: string; sessions: number; reviews_raised: number }[];
  supports: { action: InterventionKey; approved: number; resumed: number }[];
  evidence: Partial<Record<EvidenceSource, number>>;
  activities: {
    activity_id: string;
    name: string;
    class_seconds: number;
    reviews_raised: number;
  }[];
  heat: { dow: number; hour: number; count: number }[];
};

const count = (value: unknown, min = 0): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= min;
const text = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;
const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const list = (value: unknown): Record<string, unknown>[] => {
  if (!Array.isArray(value) || !value.every(isObject)) throw new Error("Invalid insights");
  return value;
};
const bad = (): never => {
  throw new Error("Invalid insights");
};

/** Strict in the same places as the Python contract: anything else is an error, not a guess. */
export function parseInsights(input: unknown): Insights {
  if (!isObject(input)) return bad();
  const { range, totals, previous } = input;
  if (!isObject(range) || !text(range.from) || !text(range.to)) return bad();
  if (!isObject(totals) || !isObject(previous)) return bad();
  for (const key of [
    "sessions",
    "class_seconds",
    "reviews_raised",
    "confirmed",
    "dismissed",
    "reviewed",
    "expired",
    "pending",
    "approved_supports",
  ]) {
    if (!count(totals[key])) return bad();
  }
  const median = totals.median_decision_seconds;
  if (median !== null && !(typeof median === "number" && Number.isFinite(median) && median >= 0))
    return bad();
  if (!count(previous.sessions) || !count(previous.reviews_raised)) return bad();
  const weekly = list(input.weekly).map((w) => {
    if (!text(w.week_start) || !/^\d{4}-\d{2}-\d{2}$/.test(w.week_start)) return bad();
    if (!count(w.sessions) || !count(w.reviews_raised)) return bad();
    return { week_start: w.week_start, sessions: w.sessions, reviews_raised: w.reviews_raised };
  });
  const supports = list(input.supports).map((s) => {
    if (!isInterventionKey(s.action) || !count(s.approved) || !count(s.resumed)) return bad();
    return { action: s.action, approved: s.approved, resumed: s.resumed };
  });
  const evidence: Insights["evidence"] = {};
  if (!isObject(input.evidence)) return bad();
  for (const [source, uses] of Object.entries(input.evidence)) {
    if (!Object.hasOwn(evidenceLabels, source) || !count(uses, 1)) return bad();
    evidence[source as EvidenceSource] = uses as number;
  }
  const activities = list(input.activities).map((a) => {
    if (!text(a.activity_id) || !text(a.name)) return bad();
    if (!count(a.class_seconds) || !count(a.reviews_raised)) return bad();
    return {
      activity_id: a.activity_id,
      name: a.name,
      class_seconds: a.class_seconds,
      reviews_raised: a.reviews_raised,
    };
  });
  const heat = list(input.heat).map((h) => {
    if (!count(h.dow) || h.dow > 6 || !count(h.hour) || h.hour > 23 || !count(h.count, 1))
      return bad();
    return { dow: h.dow, hour: h.hour, count: h.count };
  });
  return {
    range: { from: range.from, to: range.to },
    totals: {
      sessions: totals.sessions as number,
      class_seconds: totals.class_seconds as number,
      reviews_raised: totals.reviews_raised as number,
      confirmed: totals.confirmed as number,
      dismissed: totals.dismissed as number,
      reviewed: totals.reviewed as number,
      expired: totals.expired as number,
      pending: totals.pending as number,
      approved_supports: totals.approved_supports as number,
      median_decision_seconds: median as number | null,
    },
    previous: { sessions: previous.sessions as number, reviews_raised: previous.reviews_raised as number },
    weekly,
    supports,
    evidence,
    activities,
    heat,
  };
}

const MESSAGES = {
  signIn: "Sign in as a teacher to see your insights.",
  failed: "Could not load your insights. Check your connection and try again.",
} as const;

/** One request for the whole page. `tz` is the teacher's own time zone, for weekday and hour. */
export async function fetchInsights(
  client: SupabaseClient,
  range: { from: Date; to: Date },
  activity: string | null,
  tz: string,
): Promise<Insights> {
  let response;
  try {
    response = await client
      .rpc("teacher_insights", {
        p_from: range.from.toISOString(),
        p_to: range.to.toISOString(),
        p_activity: activity,
        p_tz: tz,
      })
      .abortSignal(AbortSignal.timeout(12000));
  } catch {
    throw new Error(MESSAGES.failed);
  }
  if (response.error?.code === "42501") throw new Error(MESSAGES.signIn);
  if (response.error) throw new Error(MESSAGES.failed);
  try {
    return parseInsights(response.data);
  } catch {
    throw new Error(MESSAGES.failed);
  }
}
