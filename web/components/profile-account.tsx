"use client";

import Link from "next/link";
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
    }
  }

  if (!client) return null;
  return (
    <section className="settings-row is-static" aria-label="Account">
      <span className="settings-row-body">
        <strong>Account</strong>
        <span>
          {state === "loading"
            ? "Loading…"
            : state === "signed-out"
              ? "You’re signed out."
              : (email ?? "Signed in")}
        </span>
        {error ? (
          <span className="settings-row-error" role="alert">
            {error}
          </span>
        ) : null}
      </span>
      {state === "signed-out" ? (
        <Link className="settings-row-action" href="/login">
          Sign in
        </Link>
      ) : state === "loading" ? null : (
        <button
          type="button"
          className="settings-row-action"
          disabled={state === "signing-out"}
          onClick={() => void signOut()}
        >
          {state === "signing-out" ? "Signing out…" : "Sign out"}
        </button>
      )}
    </section>
  );
}
