"use client";

import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { resolutionLabels, type TeacherReview } from "@/lib/teacher-reviews";
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
}: {
  client: SupabaseClient;
  review: TeacherReview;
  onResolved: (review: TeacherReview) => void;
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
      onResolved(await resolveTeacherReview(client, review, status));
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
      // Approving also confirms the review: it leaves the queue like "Support needed".
      onResolved({ ...review, status: "confirmed", resolved_at: new Date().toISOString() });
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
  return (
    <div className="review-actions">
      <div className="intervention-pick">
          <label htmlFor={`support-${review.id}`}>
            {review.suggested_intervention
              ? "Cues suggests a support. You decide."
              : "Choose a support to approve."}
          </label>
          <div className="intervention-row">
            <select
              id={`support-${review.id}`}
              value={support}
              disabled={!authenticated || saving !== null}
              onChange={(event) => {
                const value = event.target.value;
                setSupport(isInterventionKey(value) ? value : "");
              }}
            >
              <option value="">Pick a support…</option>
              {(Object.keys(INTERVENTION_MENU) as InterventionKey[]).map((key) => (
                <option key={key} value={key}>
                  {INTERVENTION_MENU[key]}
                  {key === review.suggested_intervention ? " (suggested)" : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="ws-pill is-dark"
              disabled={!authenticated || saving !== null || !support}
              onClick={() => void approve()}
            >
              {saving === "approve" ? "Saving…" : "Approve support"}
            </button>
          </div>
        </div>
      <div className="review-action-buttons" aria-busy={saving !== null}>
        <button
          type="button"
          className="ws-pill is-dark"
          disabled={!authenticated || saving !== null}
          onClick={() => void resolve("confirmed")}
        >
          {saving === "confirmed" ? "Saving…" : resolutionLabels.confirmed}
        </button>
        <button
          type="button"
          className="ws-pill"
          disabled={!authenticated || saving !== null}
          onClick={() => void resolve("dismissed")}
        >
          {saving === "dismissed" ? "Saving…" : resolutionLabels.dismissed}
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
