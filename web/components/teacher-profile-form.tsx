"use client";

import { useEffect, useRef, useState } from "react";
import { countryCodes, normalizeAlertPhone } from "@/lib/alert-phone";
import { createDashboardClient } from "@/lib/supabase";
import {
  saveTeacherProfile,
  syncSignupProfile,
  type TeacherProfile,
} from "@/lib/teacher-profile";
import "./teacher-profile.css";
import { DemoNotifications } from "@/components/demo-notifications";
import { WorkspaceIcon } from "@/components/workspace-icon";

/** Split a stored E.164 number back into a listed country code and the rest. */
function splitPhone(phone: string | null) {
  if (!phone) return { code: "1", number: "" };
  const match = countryCodes
    .map((country) => country.code)
    .toSorted((a, b) => b.length - a.length)
    .find((code) => phone.startsWith(`+${code}`));
  return match
    ? { code: match, number: phone.slice(match.length + 1) }
    : { code: "1", number: phone };
}

export default function TeacherProfileForm() {
  const [client] = useState(() => {
    try {
      return createDashboardClient(true);
    } catch {
      return null;
    }
  });
  const [profile, setProfile] = useState<TeacherProfile | null>(null);
  const [name, setName] = useState("");
  const [countryCode, setCountryCode] = useState("1");
  const [phone, setPhone] = useState("");
  const [state, setState] = useState<
    "loading" | "signed-out" | "ready" | "saving" | "error"
  >("loading");
  const [message, setMessage] = useState<string | null>(null);
  const locked = useRef(false);
  const userRef = useRef<string | null>(null);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    // undefined until the first auth event, so a signed-out start still resolves.
    let loadedFor: string | null | undefined = undefined;
    async function load(userId: string) {
      try {
        // Also moves a number left in sign-up metadata into the profile.
        const loaded = await syncSignupProfile(client!);
        if (cancelled || loadedFor !== userId) return;
        setProfile(loaded);
        setName(loaded.display_name ?? "");
        const parts = splitPhone(loaded.phone_number);
        setCountryCode(parts.code);
        setPhone(parts.number);
        setState("ready");
      } catch {
        if (!cancelled && loadedFor === userId) {
          setMessage("Your profile could not be loaded. Refresh to try again.");
          setState("error");
        }
      }
    }
    // Follow the session, so signing out from the Account card clears the
    // previous teacher's name and number at once.
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      const userId = session?.user.id ?? null;
      if (userId === loadedFor) return;
      loadedFor = userId;
      userRef.current = userId;
      setProfile(null);
      setName("");
      setCountryCode("1");
      setPhone("");
      setMessage(null);
      if (!userId) {
        setState("signed-out");
        return;
      }
      setState("loading");
      // Defer: Supabase calls inside this callback would wait on the auth lock.
      setTimeout(() => void load(userId), 0);
    });
    return () => {
      cancelled = true;
      data.subscription.unsubscribe();
    };
  }, [client]);

  const normalizedPhone = phone.trim()
    ? normalizeAlertPhone(countryCode, phone)
    : null;
  const phoneInvalid = phone.trim() !== "" && normalizedPhone === null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!client || locked.current || phoneInvalid) return;
    locked.current = true;
    // If the teacher signs out mid-save, the result belongs to nobody on screen.
    const savingFor = userRef.current;
    setState("saving");
    setMessage(null);
    try {
      const saved = await saveTeacherProfile(client, {
        display_name: name,
        phone_number: normalizedPhone,
      });
      if (userRef.current !== savingFor) return;
      setProfile(saved);
      setMessage("Profile saved.");
    } catch (cause) {
      if (userRef.current !== savingFor) return;
      setMessage(
        cause instanceof Error
          ? cause.message
          : "Your profile could not be saved.",
      );
    } finally {
      locked.current = false;
      if (userRef.current === savingFor) setState("ready");
    }
  }

  if (!client)
    return (
      <section className="profile-group">
        <div className="profile-card">
          <p className="profile-hint">
            Teacher accounts aren’t configured in this environment.
          </p>
        </div>
      </section>
    );
  if (state === "loading")
    return (
      <section className="profile-group" role="status">
        <div className="profile-card">
          <p className="profile-hint">Loading your profile…</p>
        </div>
      </section>
    );
  // Signed out: the Account card above offers Sign in.
  if (state === "signed-out") return null;
  if (state === "error")
    return (
      <section className="profile-group">
        <div className="profile-card">
          <p className="profile-error" role="alert">
            {message}
          </p>
        </div>
      </section>
    );
  const country = countryCodes.find((item) => item.code === countryCode);
  // Save lights up only when something changed.
  const dirty =
    name.trim() !== (profile?.display_name ?? "") ||
    normalizedPhone !== (profile?.phone_number ?? null);
  return (
    <>
      <section className="profile-group" aria-labelledby="profile-form-heading">
        <form className="profile-card profile-form" onSubmit={save}>
          <h2 id="profile-form-heading" className="profile-card-title">
            name and phone
          </h2>
          <label className="profile-field">
            <span>Name</span>
            <input
              name="display_name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="name"
              maxLength={80}
              placeholder="Ms. Rivera"
            />
          </label>
          <div className="profile-field">
            <label htmlFor="profile-phone">Mobile for alerts</label>
            <div
              className="phone-field"
              data-invalid={phoneInvalid || undefined}
            >
              {/* The native list stays for keyboards and screen readers; the
                  chip shows only the code, so the field stays compact. */}
              <span className="phone-code">
                <span aria-hidden="true">+{countryCode}</span>
                <WorkspaceIcon name="chevronDown" />
                <select
                  aria-label={`Country code, ${country ? `+${country.code} ${country.label}` : ""}`}
                  value={countryCode}
                  onChange={(event) => setCountryCode(event.target.value)}
                  autoComplete="tel-country-code"
                >
                  {countryCodes.map((item) => (
                    <option key={item.code} value={item.code}>
                      +{item.code} {item.label}
                    </option>
                  ))}
                </select>
              </span>
              <input
                id="profile-phone"
                type="tel"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                autoComplete="tel-national"
                inputMode="tel"
                maxLength={20}
                placeholder="Optional"
                aria-invalid={phoneInvalid || undefined}
                aria-describedby="profile-phone-hint"
              />
            </div>
            <p
              id="profile-phone-hint"
              className={phoneInvalid ? "profile-error" : "profile-hint"}
            >
              {phoneInvalid
                ? "Check the number and its country code."
                : "Alerts name only the seat, never images or camera data."}
            </p>
          </div>
          <div className="profile-actions">
            <p className="profile-hint" role="status" aria-live="polite">
              {message}
            </p>
            <button
              className="ws-pill is-dark"
              type="submit"
              disabled={state === "saving" || phoneInvalid || !dirty}
            >
              {state === "saving" ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </section>
      <DemoNotifications
        client={client}
        phone={profile?.phone_number ?? null}
        phoneDirty={
          normalizedPhone !== (profile?.phone_number ?? null) || phoneInvalid
        }
        profileSaving={state === "saving"}
      />
    </>
  );
}
