"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { RiArrowLeftLine, RiArrowRightLine } from "@remixicon/react";
import { createDashboardClient } from "@/lib/supabase";
import "./auth.css";

const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
  loading: () => <div className="login-companion" />,
});

type Step = "role" | "email" | "password" | "check";

const MIN_PASSWORD = 8;
const roles = ["Teacher", "Teaching assistant", "Therapist", "Something else"];

const headings: Record<"signin" | "signup", Record<Step, string>> = {
  signin: {
    role: "",
    email: "Welcome back",
    password: "Enter your password",
    check: "",
  },
  signup: {
    role: "Who’s setting up Cues?",
    email: "What’s your school email?",
    password: "Choose a password",
    check: "Check your inbox",
  },
};

const subscribeMotion = (callback: () => void) => {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
};

/** Types the heading in, with a block caret, unless motion is reduced. */
function TypedHeading({ text }: { text: string }) {
  const reduced = useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(
      () =>
        setShown((count) => {
          if (count >= text.length) window.clearInterval(timer);
          return Math.min(count + 1, text.length);
        }),
      32,
    );
    return () => window.clearInterval(timer);
  }, [reduced, text]);
  const typing = !reduced && shown < text.length;
  return (
    <h1 id="auth-heading" aria-label={text}>
      {/* The invisible copy holds the final size, so nothing below jumps. */}
      <span className="auth-heading-size" aria-hidden="true">
        {text}
      </span>
      <span className="auth-heading-typed" aria-hidden="true">
        {reduced ? text : text.slice(0, shown)}
        {typing ? <span className="auth-caret" /> : null}
      </span>
    </h1>
  );
}

export default function TeacherLogin({
  mode = "signin",
  signupEnabled = false,
}: {
  mode?: "signin" | "signup";
  signupEnabled?: boolean;
}) {
  const router = useRouter();
  const signingUp = mode === "signup";
  const [step, setStep] = useState<Step>(signingUp ? "role" : "email");
  const [role, setRole] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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

  const firstStep: Step = signingUp ? "role" : "email";
  const ready =
    step === "role"
      ? role !== null
      : step === "email"
        ? /^\S+@\S+\.\S+$/.test(email.trim())
        : step === "password"
          ? password.length >= (signingUp ? MIN_PASSWORD : 1) && !!client
          : false;

  function back() {
    setError(null);
    setStep(step === "password" ? "email" : "role");
  }

  async function submitPassword() {
    if (locked.current || !client) return;
    locked.current = true;
    setBusy(true);
    setError(null);
    try {
      if (signingUp) {
        const { data, error } = await client.auth.signUp({
          email: email.trim(),
          password,
          options: { data: { role } },
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

  function next(event: React.FormEvent) {
    event.preventDefault();
    if (!ready || busy) return;
    setError(null);
    if (step === "role") setStep("email");
    else if (step === "email") setStep("password");
    else if (step === "password") void submitPassword();
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
        {step !== firstStep && step !== "check" ? (
          <button
            className="auth-back"
            aria-label="Go back"
            disabled={busy}
            onClick={back}
          >
            <RiArrowLeftLine />
          </button>
        ) : (
          <Link className="auth-wordmark" href="/">
            Cues
          </Link>
        )}
        {switchLink}
      </header>
      <section className="auth-content" aria-labelledby="auth-heading">
        <Companion size={92} busy={busy} privacy={step === "password"} />
        <form className="auth-step" key={step} onSubmit={next} aria-busy={busy}>
          <TypedHeading text={headings[mode][step]} />
          <div className="auth-body">
            {step === "role" ? (
              <>
                <p className="auth-hint">
                  So Cues can word its suggestions for you.
                </p>
                <div className="auth-chips" role="radiogroup" aria-label="Your role">
                  {roles.map((option) => (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={role === option}
                      className="auth-chip"
                      onClick={() => setRole(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </>
            ) : step === "email" ? (
              <>
                <p className="auth-hint">
                  {signingUp
                    ? "You’ll use it to sign in to your classroom."
                    : "Use the email your teacher account was created with."}
                </p>
                <label className="sr-only" htmlFor="teacher-email">
                  Email
                </label>
                <input
                  id="teacher-email"
                  className="auth-input"
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
              </>
            ) : step === "password" ? (
              <>
                <button
                  type="button"
                  className="auth-email"
                  onClick={() => setStep("email")}
                  disabled={busy}
                >
                  {email}
                  <span>Change</span>
                </button>
                <label className="sr-only" htmlFor="teacher-password">
                  Password
                </label>
                <input
                  id="teacher-password"
                  className="auth-input"
                  name="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
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
                <p className="auth-hint" aria-live="polite">
                  {busy
                    ? signingUp
                      ? "Creating your account…"
                      : "Signing in…"
                    : "Student video never leaves the classroom laptop."}
                </p>
              </>
            ) : (
              <>
                <p className="auth-hint">
                  We sent a link to <strong>{email}</strong>. Open it to
                  confirm your account, then log in.
                </p>
                <Link className="auth-primary" href="/login">
                  Go to log in
                  <RiArrowRightLine aria-hidden="true" />
                </Link>
              </>
            )}
            {!client && step !== "check" && step !== "role" ? (
              <p className="auth-error" role="status">
                Teacher accounts aren’t configured in this environment. You
                can still <Link href="/dashboard">open the classroom</Link>.
              </p>
            ) : null}
            {error ? (
              <p className="auth-error" role="alert">
                {error}
              </p>
            ) : null}
            {step !== "check" ? (
              <button
                className="auth-next"
                type="submit"
                data-ready={ready || undefined}
                disabled={!ready || busy}
                aria-label={
                  step === "password"
                    ? signingUp
                      ? "Create account"
                      : "Sign in"
                    : "Continue"
                }
              >
                <RiArrowRightLine />
              </button>
            ) : null}
          </div>
        </form>
      </section>
    </main>
  );
}
