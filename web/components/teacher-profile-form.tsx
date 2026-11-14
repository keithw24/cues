"use client";

import Link from "next/link";
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
  const [email, setEmail] = useState<string | null>(null);
  const [profile, setProfile] = useState<TeacherProfile | null>(null);
  const [name, setName] = useState("");
  const [countryCode, setCountryCode] = useState("1");
  const [phone, setPhone] = useState("");
  const [state, setState] = useState<
    "loading" | "signed-out" | "ready" | "saving" | "error"
  >("loading");
  const [message, setMessage] = useState<string | null>(null);
  const locked = useRef(false);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    async function load() {
      const { data } = await client!.auth.getUser();
      if (cancelled) return;
      if (!data.user) {
        setState("signed-out");
        return;
      }
      setEmail(data.user.email ?? null);
      try {
        // Also moves a number left in sign-up metadata into the profile.
        const loaded = await syncSignupProfile(client!);
        if (cancelled) return;
        setProfile(loaded);
        setName(loaded.display_name ?? "");
        const parts = splitPhone(loaded.phone_number);
        setCountryCode(parts.code);
        setPhone(parts.number);
        setState("ready");
      } catch {
        if (!cancelled) {
          setMessage("Your profile could not be loaded. Refresh to try again.");
          setState("error");
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
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
    setState("saving");
    setMessage(null);
    try {
      const saved = await saveTeacherProfile(client, {
        display_name: name,
        phone_number: normalizedPhone,
      });
      setProfile(saved);
      setMessage("Profile saved.");
    } catch (cause) {
      setMessage(
        cause instanceof Error
          ? cause.message
          : "Your profile could not be saved.",
      );
    } finally {
      locked.current = false;
      setState("ready");
    }
  }

  if (!client)
    return (
      <div className="integration-details">
        <p>Teacher accounts aren’t configured in this environment.</p>
      </div>
    );
  if (state === "loading")
    return (
      <div className="integration-details" role="status">
        <p>Loading your profile…</p>
      </div>
    );
  if (state === "signed-out")
    return (
      <div className="integration-details">
        <p>Sign in to manage your profile.</p>
        <Link className="quiet-link" href="/login">
          Teacher sign in
        </Link>
      </div>
    );
  if (state === "error")
    return (
      <div className="integration-details">
        <p role="alert">{message}</p>
      </div>
    );
  return (
    <><form className="integration-details profile-form" onSubmit={save}>
      <dl>
        <div>
          <dt>Email</dt>
          <dd>{email ?? "Unavailable"}</dd>
        </div>
      </dl>
      <label className="profile-field">
        <span>Display name</span>
        <input
          name="display_name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="name"
          maxLength={80}
          placeholder="Ms. Rivera"
        />
      </label>
      <fieldset className="profile-field">
        <legend>Mobile number for alerts</legend>
        <div className="profile-phone">
          <label className="sr-only" htmlFor="profile-country">
            Country code
          </label>
          <select
            id="profile-country"
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
          <label className="sr-only" htmlFor="profile-phone">
            Mobile number
          </label>
          <input
            id="profile-phone"
            type="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            autoComplete="tel-national"
            inputMode="tel"
            maxLength={20}
            aria-invalid={phoneInvalid || undefined}
            aria-describedby="profile-phone-hint"
          />
        </div>
        <p id="profile-phone-hint" className="integration-note">
          {phoneInvalid
            ? "Check the number and its country code."
            : "Optional. Alerts carry only the seat and task, never images."}
        </p>
      </fieldset>
      <button
        className="primary-button"
        type="submit"
        disabled={state === "saving" || phoneInvalid}
      >
        {state === "saving" ? "Saving…" : "Save profile"}
      </button>
      {message ? (
        <p role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
      {profile?.phone_number ? (
        <p className="integration-note">Saved as {profile.phone_number}</p>
      ) : null}
    </form>
    <DemoNotifications client={client} phone={profile?.phone_number ?? null}
      phoneDirty={normalizedPhone !== (profile?.phone_number ?? null) || phoneInvalid}
      profileSaving={state === "saving"} />
    </>
  );
}
