"use client";

import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { TeacherReview } from "@/lib/teacher-reviews";
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
  const locked = useRef(false);
  const [saving, setSaving] = useState<ReviewResolution | null>(null);
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
          : "Could not save this review action.",
      );
    } finally {
      locked.current = false;
      setSaving(null);
    }
  }
  if (review.status !== "pending") return null;
  return (
    <div className="review-actions">
      <div className="review-action-buttons" aria-busy={saving !== null}>
        <button
          type="button"
          className="text-button"
          disabled={!authenticated || saving !== null}
          onClick={() => void resolve("confirmed")}
        >
          {saving === "confirmed" ? "Saving…" : "Needs attention"}
        </button>
        <button
          type="button"
          className="text-button"
          disabled={!authenticated || saving !== null}
          onClick={() => void resolve("dismissed")}
        >
          {saving === "dismissed" ? "Saving…" : "Dismiss"}
        </button>
      </div>
      {!authenticated ? <p role="status">Sign in to resolve teacher reviews.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}
