"use client";

import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { TeacherReview } from "@/lib/teacher-reviews";
import { markSeatReviewed } from "@/lib/seat-review";
import {
  INTERVENTION_MENU,
  approveIntervention,
  isInterventionKey,
  type InterventionKey,
} from "@/lib/interventions";
import {
  resolveTeacherReview,
  type ReviewResolution,
} from "@/lib/teacher-review-actions";

export function TeacherReviewActions({
  client,
  review,
  onResolved,
  onMarked,
}: {
  client: SupabaseClient;
  review: TeacherReview;
  onResolved: (review: TeacherReview) => void;
  /** Called once the child is also marked reviewed (back to working, timer restarted). */
  onMarked?: (seatId: string) => void;
}) {
  const [support, setSupport] = useState<InterventionKey | "">(
    review.suggested_intervention ?? "",
  );
  const locked = useRef(false);
  const [saving, setSaving] = useState<ReviewResolution | "approve" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => {
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAuthenticated(Boolean(session?.user));
    });
    return () => data.subscription.unsubscribe();
  }, [client]);
  async function resolve(status: ReviewResolution) {
    if (!authenticated || locked.current || review.status !== "pending") return;
    locked.current = true;
    setSaving(status);
    setError(null);
    try {
      const resolved = await resolveTeacherReview(client, review, status);
      // Either answer is the teacher's check-in: put the child back to working too.
      await markSeatReviewed(client, review.session_id, review.seat_id);
      onResolved(resolved);
      onMarked?.(review.seat_id);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Couldn’t save that. Try again.",
      );
    } finally {
      locked.current = false;
      setSaving(null);
    }
  }
  async function approve() {
    if (!authenticated || locked.current || review.status !== "pending") return;
    if (!isInterventionKey(support)) return;
    locked.current = true;
    setSaving("approve");
    setError(null);
    try {
      await approveIntervention(client, review.id, support);
      // Approving also confirms the review and is the teacher's check-in: reset the child.
      await markSeatReviewed(client, review.session_id, review.seat_id);
      onResolved({ ...review, status: "confirmed", resolved_at: new Date().toISOString() });
      onMarked?.(review.seat_id);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Couldn’t save that. Try again.",
      );
    } finally {
      locked.current = false;
      setSaving(null);
    }
  }
  if (review.status !== "pending") return null;
  const busy = !authenticated || saving !== null;
  return (
    <div className="review-actions">
      <div className="intervention-pick">
        <div className="intervention-row">
          <select
            id={`support-${review.id}`}
            aria-label="Support"
            value={support}
            disabled={busy}
            onChange={(event) => {
              const value = event.target.value;
              setSupport(isInterventionKey(value) ? value : "");
            }}
          >
            <option value="">Pick a support…</option>
            {(Object.keys(INTERVENTION_MENU) as InterventionKey[]).map((key) => (
              <option key={key} value={key}>
                {key === review.suggested_intervention ? "Suggested: " : ""}
                {INTERVENTION_MENU[key]}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="review-action-buttons" aria-busy={saving !== null}>
        <button
          type="button"
          className="ws-pill is-dark"
          disabled={busy || !support}
          onClick={() => void approve()}
        >
          {saving === "approve" ? "Saving…" : "Approve"}
        </button>
        <button
          type="button"
          className="ws-pill"
          disabled={busy}
          onClick={() => void resolve("dismissed")}
        >
          {saving === "dismissed" ? "Saving…" : "Not needed"}
        </button>
      </div>
      {!authenticated ? (
        <p className="person-note" role="status">
          Sign in to record your decision.
        </p>
      ) : null}
      {error ? (
        <p className="person-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
