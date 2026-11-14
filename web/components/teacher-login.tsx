"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiLock2Line,
  RiMailLine,
} from "@remixicon/react";
import { createDashboardClient } from "@/lib/supabase";
import "./auth.css";

const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
  loading: () => <div className="login-companion" />,
});

type Step = "email" | "password" | "check";

const MIN_PASSWORD = 8;

const headings = {
  signin: {
    email: "Welcome back. What’s your email?",
    password: "Enter your password",
  },
  signup: {
    email: "Let’s set up your classroom. What’s your email?",
    password: "Choose a password",
  },
} as const;

export default function TeacherLogin({
  mode = "signin",
  signupEnabled = false,
}: {
  mode?: "signin" | "signup";
  signupEnabled?: boolean;
}) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = useRef(false);
  const [client] = useState(() => {
    try {
      return createDashboardClient(true);
    } catch {
      return null;
    }
  });
  const signingUp = mode === "signup";

  async function submitPassword(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked.current || !client) return;
    const password = String(
      new FormData(event.currentTarget).get("password") ?? "",
    );
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      if (signingUp) {
        const { data, error } = await client.auth.signUp({
          email: email.trim(),
          password,
        });
        if (error)
          setError(
            error.status === 422
              ? "That email already has an account. Try logging in instead."
              : "We couldn’t create your account. Check your details and try again.",
          );
        // Projects that confirm email return no session until the link is opened.
        else if (!data.session) setStep("check");
        else {
          router.push("/dashboard");
          router.refresh();
        }
      } else {
        const { error } = await client.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error)
          setError(
            "We couldn’t sign you in. Check your email and password, then try again.",
          );
        else {
          router.push("/dashboard");
          router.refresh();
        }
      }
    } catch {
      setError("Couldn’t connect. Check your connection and try again.");
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  const switchLink = signingUp ? (
    <Link className="auth-switch" href="/login">
      Log in
    </Link>
  ) : signupEnabled ? (
    <Link className="auth-switch" href="/signup">
      Sign up
    </Link>
  ) : null;

  return (
    <main id="main-content" className="auth-page">
      <header className="auth-header">
        <Link className="auth-wordmark" href="/">
          Cues
        </Link>
        {switchLink}
      </header>
      {step === "password" ? (
        <button
          className="auth-back"
          aria-label="Go back"
          disabled={busy}
          onClick={() => {
            setError(null);
            setStep("email");
          }}
        >
          <RiArrowLeftLine />
        </button>
      ) : null}
      <section className="auth-content" aria-labelledby="auth-heading">
        <Companion busy={busy} privacy={step === "password"} />
        <div className="auth-step" key={step}>
          <h1 id="auth-heading">
            {step === "check" ? "Check your inbox" : headings[mode][step]}
          </h1>
          {step === "email" ? (
            <form
              className="auth-form"
              onSubmit={(event) => {
                event.preventDefault();
                setStep("password");
              }}
            >
              <p className="auth-hint">
                {signingUp
                  ? "You’ll use it to sign in to your teacher dashboard."
                  : "Use the email your teacher account was created with."}
              </p>
              <label className="sr-only" htmlFor="teacher-email">
                Teacher email
              </label>
              <div className="auth-field">
                <RiMailLine aria-hidden="true" />
                <input
                  id="teacher-email"
                  type="email"
                  name="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@school.edu"
                  autoComplete="username"
                  required
                  autoFocus
                  maxLength={254}
                />
                <button className="auth-next" type="submit" aria-label="Continue">
                  <RiArrowRightLine />
                </button>
              </div>
            </form>
          ) : step === "password" ? (
            <form className="auth-form" onSubmit={submitPassword} aria-busy={busy}>
              <button
                type="button"
                className="auth-chip"
                onClick={() => {
                  setStep("email");
                  setError(null);
                }}
                disabled={busy}
              >
                {email}
                <span>Change</span>
              </button>
              <label className="sr-only" htmlFor="teacher-password">
                Password
              </label>
              <div className="auth-field">
                <RiLock2Line aria-hidden="true" />
                <input
                  id="teacher-password"
                  name="password"
                  type="password"
                  placeholder={
                    signingUp
                      ? `At least ${MIN_PASSWORD} characters`
                      : "Your password"
                  }
                  autoComplete={signingUp ? "new-password" : "current-password"}
                  minLength={signingUp ? MIN_PASSWORD : undefined}
                  required
                  autoFocus
                  disabled={busy}
                />
                <button
                  className="auth-next"
                  type="submit"
                  aria-label={signingUp ? "Create account" : "Sign in"}
                  disabled={busy || !client}
                >
                  <RiArrowRightLine />
                </button>
              </div>
              <p className="auth-hint" aria-live="polite">
                {busy
                  ? signingUp
                    ? "Creating your account…"
                    : "Signing in…"
                  : signingUp
                    ? "Your camera never leaves the classroom laptop."
                    : " "}
              </p>
            </form>
          ) : (
            <div className="auth-form">
              <p className="auth-hint">
                We sent a link to <strong>{email}</strong>. Open it to confirm
                your account, then log in.
              </p>
              <Link className="auth-primary" href="/login">
                Go to log in
                <RiArrowRightLine />
              </Link>
            </div>
          )}
          {!client && step !== "check" ? (
            <p className="auth-error" role="status">
              Teacher accounts aren’t configured in this environment. You can
              still <Link href="/dashboard">open the classroom</Link>.
            </p>
          ) : null}
          {error ? (
            <p className="auth-error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      </section>
      <footer className="auth-footer">
        <RiLock2Line aria-hidden="true" />
        Camera stays local. You stay in control.
      </footer>
    </main>
  );
}
