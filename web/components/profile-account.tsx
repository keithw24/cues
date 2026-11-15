"use client";

import Link from "next/link";
import { forgetCompanionCounts } from "@/lib/companion";
import { forgetMarked } from "@/lib/classroom-view";
import { useEffect, useRef, useState } from "react";
import { createDashboardClient } from "@/lib/supabase";

// The teacher's account on the Profile page: who is signed in, and the one
// place to sign out. Signing out stays here; it never jumps to the sign-in page.
export default function ProfileAccount() {
  const [client] = useState(() => {
    try {
      return createDashboardClient(true);
    } catch {
      return null;
    }
  });
  const [email, setEmail] = useState<string | null>(null);
  const [state, setState] = useState<
    "loading" | "signed-in" | "signed-out" | "signing-out"
  >("loading");
  const [error, setError] = useState<string | null>(null);
  const locked = useRef(false);

  useEffect(() => {
    if (!client) return;
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
      setState(session?.user ? "signed-in" : "signed-out");
    });
    return () => data.subscription.unsubscribe();
  }, [client]);

  async function signOut() {
    if (!client || locked.current) return;
    locked.current = true;
    setState("signing-out");
    setError(null);
    const { error: failed } = await client.auth.signOut();
    locked.current = false;
    if (failed) {
      setError("Could not sign out. Try again.");
      setState("signed-in");
      return;
    }
    // The next teacher in this tab starts with no remembered queue.
    try {
      forgetCompanionCounts(window.sessionStorage);
      forgetMarked(window.sessionStorage);
    } catch {}
  }

  if (!client) return null;
  return (
    <section className="profile-group" aria-labelledby="account-heading">
      <div className="profile-card profile-account">
        <h2 id="account-heading" className="sr-only">
          Account
        </h2>
        <span className="row-avatar is-large" aria-hidden="true">
          {email ? email[0].toUpperCase() : "?"}
        </span>
        <span className="profile-account-body">
          <strong>
            {state === "loading"
              ? "Loading…"
              : state === "signed-out"
                ? "You’re signed out"
                : (email ?? "Signed in")}
          </strong>
          <span>
            {state === "signed-out"
              ? "Sign in to see your classroom."
              : "Teacher account"}
          </span>
          {error ? (
            <span className="profile-error" role="alert">
              {error}
            </span>
          ) : null}
        </span>
        {state === "signed-out" ? (
          <Link className="ws-pill is-dark" href="/login">
            Sign in
          </Link>
        ) : state === "loading" ? null : (
          <button
            type="button"
            className="ws-pill"
            disabled={state === "signing-out"}
            onClick={() => void signOut()}
          >
            {state === "signing-out" ? "Signing out…" : "Sign out"}
          </button>
        )}
      </div>
    </section>
  );
}
