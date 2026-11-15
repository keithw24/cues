"use client";

import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { markSeatReviewed } from "@/lib/seat-review";
import { resolutionLabels } from "@/lib/teacher-reviews";

/**
 * "Mark as reviewed" for a flagged child. It closes their open review requests on every
 * page, puts them back to working, and restarts the timer before the next review prompt.
 */
export function MarkReviewedButton({
  client,
  sessionId,
  seatId,
  label = "Mark as reviewed",
  variant = "text",
  onMarked,
}: {
  client: SupabaseClient;
  sessionId: string;
  seatId: string;
  label?: string;
  variant?: "text" | "live";
  onMarked?: (seatId: string) => void;
}) {
  // A synchronous lock, as in TeacherReviewActions, so a double click marks once.
  const locked = useRef(false);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => {
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAuthenticated(Boolean(session?.user));
    });
    return () => data.subscription.unsubscribe();
  }, [client]);
  async function mark() {
    if (!authenticated || locked.current) return;
    locked.current = true;
    setSaving(true);
    setError(null);
    try {
      await markSeatReviewed(client, sessionId, seatId);
      setDone(true);
      onMarked?.(seatId);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not mark as reviewed.",
      );
    } finally {
      locked.current = false;
      setSaving(false);
    }
  }
  return (
    <div className="mark-reviewed" aria-busy={saving}>
      <button
        type="button"
        className={variant === "live" ? "ws-pill is-dark" : "ws-pill"}
        disabled={!authenticated || saving || done}
        onClick={() => void mark()}
      >
        {saving ? "Saving…" : done ? "Marked as reviewed" : label}
      </button>
      {!authenticated ? (
        <p className="person-note" role="status">
          Sign in to mark this as reviewed.
        </p>
      ) : null}
      {done ? (
        <p className="person-note" role="status">
          They’ll show as working again in a moment.
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

/**
 * Support needed / No support needed for a person the camera flagged before Cues
 * has asked about them (web.review_waiting). There is no review request to
 * resolve, so either answer closes the flag the same way Mark as reviewed does:
 * the person leaves Attention and vision puts them back to working.
 */
export function FlagDecisionButtons({
  client,
  sessionId,
  seatId,
  onDecided,
}: {
  client: SupabaseClient;
  sessionId: string;
  seatId: string;
  onDecided?: (seatId: string) => void;
}) {
  const locked = useRef(false);
  const [saving, setSaving] = useState<"confirmed" | "dismissed" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => {
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAuthenticated(Boolean(session?.user));
    });
    return () => data.subscription.unsubscribe();
  }, [client]);
  async function decide(choice: "confirmed" | "dismissed") {
    if (!authenticated || locked.current) return;
    locked.current = true;
    setSaving(choice);
    setError(null);
    try {
      await markSeatReviewed(client, sessionId, seatId);
      onDecided?.(seatId);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Couldn’t save that. Try again.",
      );
    } finally {
      locked.current = false;
      setSaving(null);
    }
  }
  return (
    <div className="review-actions">
      <div className="review-action-buttons" aria-busy={saving !== null}>
        <button
          type="button"
          className="ws-pill is-dark"
          disabled={!authenticated || saving !== null}
          onClick={() => void decide("confirmed")}
        >
          {saving === "confirmed" ? "Saving…" : resolutionLabels.confirmed}
        </button>
        <button
          type="button"
          className="ws-pill"
          disabled={!authenticated || saving !== null}
          onClick={() => void decide("dismissed")}
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
