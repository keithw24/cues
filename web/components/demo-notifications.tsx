"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { notificationState, readNotificationSettings, requestDemoNotifications, sendTestNotification,
  NotificationSignInRequired, type NotificationSettings } from "@/lib/notification-settings";

export function DemoNotifications({client, phone, phoneDirty, profileSaving}: {
  client: SupabaseClient; phone: string | null; phoneDirty: boolean; profileSaving: boolean;
}) {
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [authoritativePhone, setAuthoritativePhone] = useState<string | null>(null);
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentPhone, setConsentPhone] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [signedOut, setSignedOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const locked = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    let cancelled = false;
    let sequence = 0;
    const invalidate = () => { generation.current++; };
    invalidate();
    async function refresh() {
      if (locked.current) return;
      const id = ++sequence;
      const current = generation.current;
      try {
        const next = await readNotificationSettings(client);
        if (cancelled || id !== sequence || current !== generation.current || locked.current) return;
        setSettings(next.settings); setAuthoritativePhone(next.phone);
        setSignedOut(false); setError(null); setLoading(false);
      } catch (cause) {
        if (cancelled || id !== sequence || current !== generation.current) return;
        setSettings(null); setLoading(false);
        setSignedOut(cause instanceof NotificationSignInRequired);
        setError("Notification status could not be loaded. Please retry.");
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const {data} = client.auth.onAuthStateChange(() => {
      invalidate(); sequence++; setSettings(null); setConsent(false);
      setFirst(""); setLast(""); setLoading(true);
      const handle = setTimeout(() => { timers.delete(handle); if (!cancelled) void refresh(); }, 0);
      timers.add(handle);
    });
    return () => {cancelled = true; invalidate(); clearInterval(timer);
      timers.forEach(clearTimeout); window.removeEventListener("focus", focus); data.subscription.unsubscribe();};
  }, [client, phone, reload]);
  const state = notificationState(settings, phone === authoritativePhone ? phone : null, phoneDirty);
  const consentValid = consent && consentPhone === phone;
  const canTest = settings?.notification_opt_in && settings.notification_phone === phone
    && phone === authoritativePhone && !!phone && !phoneDirty;
  async function testNotification() {
    if (locked.current || !canTest || profileSaving) return;
    locked.current = true; setSaving(true); setError(null); setTestMessage(null);
    const current = ++generation.current;
    try {
      const status = await sendTestNotification(client);
      if (current !== generation.current) return;
      setSettings(previous => previous ? {...previous,
        photon_registration_status: status === "registered" ? "registered" : "registering"} : previous);
      setTestMessage(status === "registered" ? "Test notification sent." :
        "Notifications are not active yet. Finish activation and try again.");
    } catch (cause) {
      if (current !== generation.current) return;
      setSignedOut(cause instanceof NotificationSignInRequired);
      setError("Notification test failed. Check activation and try again.");
    } finally {locked.current = false; setSaving(false);}
  }
  async function submit(optIn: boolean) {
    if (locked.current || profileSaving || (optIn && (phoneDirty || !consentValid || !first.trim() || !last.trim() || !phone))) return;
    locked.current = true; setSaving(true); setError(null);
    generation.current++;
    const current = generation.current;
    try {
      const result = await requestDemoNotifications(client, {opt_in: optIn, first_name: first, last_name: last});
      if (current !== generation.current) return;
      setSettings({notification_opt_in: optIn, notification_phone: optIn ? phone : null,
        photon_registration_status: result === "pending" ? "registering" : result === "registered" ? "registered" : "unregistered",
        first_name: first, last_name: last});
      setAuthoritativePhone(phone); setConsent(false);
    } catch (cause) {
      if (current !== generation.current) return;
      setSignedOut(cause instanceof NotificationSignInRequired);
      setError("Notification settings could not be saved. Please retry.");
    } finally {locked.current = false; setSaving(false);}
  }
  // One status, said once: a pill in the header and a sentence under it.
  const pill = loading ? "Loading…" : state === "enabled" ? "On" : state === "activating" ? "Activating"
    : state === "activation failed" ? "Not active" : "Off";
  const summary = !phone ? "Save a phone number in your profile first."
    : state === "enabled" ? `Notifications enabled for ${phone}.`
    : state === "activating" ? "Notifications are being activated for this phone."
    : state === "activation failed" ? "Notifications could not be activated yet."
    : `Get a text at ${phone} when a student needs you. Texts name only the seat, never images.`;
  const showOptIn = !settings?.notification_opt_in || state === "not enabled" || state === "activation failed";
  return <section className="settings-panel profile-form" aria-labelledby="demo-notifications-heading" aria-busy={saving}>
    <header className="profile-card-head">
      <h2 id="demo-notifications-heading">Demo notifications</h2>
      {signedOut ? null : <span className={`profile-status is-${state.replace(" ", "-")}`}>{pill}</span>}
    </header>
    {signedOut ? <><p>Sign in to manage demo notifications.</p><Link href="/login">Teacher sign in</Link></> : <>
      <p className="profile-hint" role="status" aria-live="polite">{loading ? "Loading notification status…" : summary}</p>
      {phoneDirty ? <p className="profile-hint">Save your profile phone before enabling notifications. A new phone requires fresh opt-in.</p> : null}
      {showOptIn ? <>
        <div className="profile-pair">
          <label className="profile-field"><span>First name</span><input value={first} onChange={e => setFirst(e.target.value)} maxLength={80} autoComplete="given-name" disabled={saving} /></label>
          <label className="profile-field"><span>Last name</span><input value={last} onChange={e => setLast(e.target.value)} maxLength={80} autoComplete="family-name" disabled={saving} /></label>
        </div>
        <label className="profile-check"><input type="checkbox" checked={consentValid && !phoneDirty} onChange={e => {setConsent(e.target.checked); setConsentPhone(phone);}} disabled={saving || phoneDirty || !phone} /> I want to receive Cues demo notifications</label>
      </> : null}
      <div className="profile-actions">
        {showOptIn ? <button type="button" className="primary-button" onClick={() => void submit(true)} disabled={loading || saving || profileSaving || phoneDirty || !phone || !consentValid || !first.trim() || !last.trim()}>{saving ? "Saving…" : "Enable notifications"}</button> : null}
        {canTest ? <button type="button" onClick={() => void testNotification()} disabled={loading || saving || profileSaving}>Send test notification</button> : null}
        {settings?.notification_opt_in ? <button type="button" onClick={() => void submit(false)} disabled={saving || profileSaving}>Disable notifications</button> : null}
      </div>
      {canTest && testMessage ? <p className="profile-hint" role="status">{testMessage}</p> : null}
    </>}
    {error ? <div className="profile-actions"><p className="settings-row-error" role="alert">{error}</p><button type="button" disabled={saving} onClick={() => setReload(n => n + 1)}>Refresh notification status</button></div> : null}
  </section>;
}
