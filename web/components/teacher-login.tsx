"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  RiArrowDownSLine,
  RiArrowLeftLine,
  RiArrowRightLine,
} from "@remixicon/react";
import CuesMark from "@/components/cues-mark";
import TypedHeading from "@/components/typed-heading";
import { countryCodes, normalizeAlertPhone } from "@/lib/alert-phone";
import { createDashboardClient } from "@/lib/supabase";
import { syncSignupProfile } from "@/lib/teacher-profile";
import { ThemeToggle } from "@/components/theme-toggle";
import "./auth.css";

const Companion = dynamic(() => import("@/components/login-companion"), {
  ssr: false,
  loading: () => <div className="login-companion" />,
});

type Step = "role" | "email" | "phone" | "password" | "check";

const MIN_PASSWORD = 8;
const roles = ["Teacher", "Teaching assistant", "Therapist", "Something else"];

const headings: Record<"signin" | "signup", Record<Step, string>> = {
  signin: {
    role: "",
    email: "Welcome back",
    phone: "",
    password: "Enter your password",
    check: "",
  },
  signup: {
    role: "Who’s setting up Cues?",
    email: "What’s your school email?",
    phone: "Where should Cues text you?",
    password: "Choose a password",
    check: "Check your inbox",
  },
};

export default function TeacherLogin({
  mode = "signin",
  signupEnabled = false,
  phoneEnabled = false,
  profileEnabled = false,
  themeToggleEnabled = false,
}: {
  mode?: "signin" | "signup";
  signupEnabled?: boolean;
  /** Ask for a mobile number Photon can text alerts to. */
  phoneEnabled?: boolean;
  /** Move the sign-up number into teacher_profiles once signed in. */
  profileEnabled?: boolean;
  themeToggleEnabled?: boolean;
}) {
  const router = useRouter();
  const signingUp = mode === "signup";
  const [step, setStep] = useState<Step>(signingUp ? "role" : "email");
  const [role, setRole] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [countryCode, setCountryCode] = useState("1");
  const [phone, setPhone] = useState("");
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
        : step === "phone"
          ? normalizeAlertPhone(countryCode, phone) !== null
          : step === "password"
            ? password.length >= (signingUp ? MIN_PASSWORD : 1) && !!client
            : false;
  const askPhone = signingUp && phoneEnabled;

  function back() {
    setError(null);
    setStep(
      step === "password"
        ? askPhone
          ? "phone"
          : "email"
        : step === "phone"
          ? "email"
          : "role",
    );
  }

  async function enterClassroom() {
    if (profileEnabled && client)
      // Best effort: the classroom still opens, and the profile page can retry.
      await syncSignupProfile(client).catch(() => null);
    router.push("/dashboard");
    router.refresh();
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
          options: {
            // Photon reads alert_phone (E.164) to text this teacher.
            data: {
              role,
              ...(askPhone
                ? { alert_phone: normalizeAlertPhone(countryCode, phone) }
                : {}),
            },
            // The link in the confirmation email opens Cues' own welcome page.
            emailRedirectTo: `${window.location.origin}/auth/confirmed`,
          },
        });
        if (error)
          setError(
            error.status === 422
              ? "That email already has an account. Try logging in instead."
              : "We couldn’t create your account. Check your details and try again.",
          );
        // Projects that confirm email return no session until the link is opened.
        else if (!data.session) setStep("check");
        else await enterClassroom();
      } else {
        const { error } = await client.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error)
          setError(
            "We couldn’t sign you in. Check your email and password, then try again.",
          );
        else await enterClassroom();
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
    else if (step === "email") setStep(askPhone ? "phone" : "password");
    else if (step === "phone") setStep("password");
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
          <Link className="auth-wordmark" href="/" aria-label="Cues home">
            <CuesMark size={28} />
          </Link>
        )}
        <div className="auth-header-actions">
          {themeToggleEnabled ? (
            <ThemeToggle pageDefault="light" className="auth-theme-toggle" />
          ) : null}
          {switchLink}
        </div>
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
            ) : step === "phone" ? (
              <>
                <p className="auth-hint">
                  Photon texts you when a student may need a hand: just the
                  seat, never images.
                </p>
                <div className="auth-phone">
                  <label className="sr-only" htmlFor="teacher-country">
                    Country code
                  </label>
                  <select
                    id="teacher-country"
                    value={countryCode}
                    onChange={(event) => setCountryCode(event.target.value)}
                    autoComplete="tel-country-code"
                  >
                    {countryCodes.map((country) => (
                      <option key={country.code} value={country.code}>
                        +{country.code} {country.label}
                      </option>
                    ))}
                  </select>
                  <span className="auth-phone-code" aria-hidden="true">
                    +{countryCode}
                    <RiArrowDownSLine />
                  </span>
                  <label className="sr-only" htmlFor="teacher-phone">
                    Mobile number
                  </label>
                  <input
                    id="teacher-phone"
                    type="tel"
                    name="phone"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder={countryCode === "1" ? "(555) 123-4567" : "Mobile number"}
                    autoComplete="tel-national"
                    inputMode="tel"
                    required
                    autoFocus
                    maxLength={20}
                  />
                </div>
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
