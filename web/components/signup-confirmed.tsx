"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RiArrowRightLine } from "@remixicon/react";
import TypedHeading from "@/components/typed-heading";
import { createDashboardClient } from "@/lib/supabase";
import "./auth.css";

const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
  loading: () => <div className="login-companion" />,
});

type State = "confirming" | "done" | "failed";

const copy: Record<State, { heading: string; hint: string }> = {
  confirming: {
    heading: "Confirming your email",
    hint: "This only takes a moment.",
  },
  done: {
    heading: "You’re all set",
    hint: "Your account is confirmed. Your classroom is ready when you are.",
  },
  failed: {
    heading: "That link didn’t work",
    hint: "It may have expired or already been used. Log in, or sign up again for a new link.",
  },
};

/** Where the link in Supabase's confirmation email lands. */
export default function SignupConfirmed() {
  const [state, setState] = useState<State>("confirming");

  useEffect(() => {
    let cancelled = false;
    async function confirm() {
      // Supabase's implicit flow puts the session (or an error) in the hash.
      const params = new URLSearchParams(window.location.hash.slice(1));
      const accessToken = params.get("access_token");
      const refreshToken = params.get("refresh_token");
      // Keep the tokens out of the address bar and the browser history.
      window.history.replaceState(null, "", window.location.pathname);
      if (params.get("error") || !accessToken || !refreshToken) {
        if (!cancelled) setState("failed");
        return;
      }
      try {
        const client = createDashboardClient(true);
        const { error } = await client.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        if (!cancelled) setState(error ? "failed" : "done");
      } catch {
        if (!cancelled) setState("failed");
      }
    }
    void confirm();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main id="main-content" className="auth-page">
      <header className="auth-header">
        <Link className="auth-wordmark" href="/">
          Cues
        </Link>
      </header>
      <section className="auth-content" aria-labelledby="auth-heading">
        <Companion size={92} busy={state === "confirming"} />
        <div className="auth-step" key={state} aria-live="polite">
          <TypedHeading text={copy[state].heading} />
          <div className="auth-body">
            <p className="auth-hint">{copy[state].hint}</p>
            {state === "done" ? (
              <Link className="auth-primary" href="/dashboard">
                Open your classroom
                <RiArrowRightLine aria-hidden="true" />
              </Link>
            ) : state === "failed" ? (
              <Link className="auth-primary" href="/login">
                Go to log in
                <RiArrowRightLine aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
