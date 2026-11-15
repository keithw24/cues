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
  const shownUser = useRef<string | null | undefined>(undefined);
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
    // Reset the form only for a different account: tab focus, token refresh and
    // this effect re-running all report the same teacher again.
    const {data} = client.auth.onAuthStateChange((_event, session) => {
      const user = session?.user.id ?? null;
      if (shownUser.current !== undefined && user === shownUser.current) return;
      const firstEvent = shownUser.current === undefined;
      shownUser.current = user;
      if (firstEvent) return;
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
      setAuthoritativePhone(phone); setConsent(false); setAsking(false);
    } catch (cause) {
      if (current !== generation.current) return;
      setSignedOut(cause instanceof NotificationSignInRequired);
      setError("Notification settings could not be saved. Please retry.");
    } finally {locked.current = false; setSaving(false);}
  }
  // One switch says on or off; one short line says what that means. The switch
  // follows the saved opt-in, so turning it off always opts out, even while a new
  // number is being edited or activation has not finished.
  const on = Boolean(settings?.notification_opt_in);
  const [asking, setAsking] = useState(false);
  const summary = loading ? "Loading…"
    : !phone ? "Add a mobile number above to get texts."
    : state === "enabled" ? `Notifications enabled for ${phone}.`
    : state === "activating" ? "Notifications are being activated for this phone."
    : state === "activation failed" ? "Notifications could not be activated yet."
    : on ? "Notifications are on but not active for this number yet."
    : "Get a text when a student needs you. Texts name only the seat, never images.";
  // Opting in (or retrying) asks for a name and consent first; off saves at once.
  const showOptIn = asking && (!settings?.notification_opt_in || state === "not enabled" || state === "activation failed");
  const retry = on && (state === "activation failed" || state === "not enabled") && !phoneDirty && !!phone;
  const toggle = () => {
    if (on) void submit(false);
    else setAsking((value) => !value);
  };
  return <section id="notifications" className="profile-group" aria-labelledby="demo-notifications-heading" aria-busy={saving}>
    <div className="profile-card profile-form">
      <h2 id="demo-notifications-heading" className="sr-only">Text alerts</h2>
      {signedOut ? <div className="alerts-head">
        <div className="alerts-copy"><strong>demo notifications</strong><p className="profile-hint">Sign in to manage demo notifications.</p></div>
        <Link className="ws-pill is-dark" href="/login">Sign in</Link>
      </div> : <>
        <div className="alerts-head">
          <div className="alerts-copy">
            <strong>demo notifications</strong>
            <p className="profile-hint" role="status" aria-live="polite">{summary}</p>
          </div>
          <button type="button" role="switch" className="ws-switch"
            aria-checked={on || showOptIn}
            aria-label={on ? "Disable notifications" : "Enable notifications"}
            onClick={toggle}
            disabled={loading || saving || profileSaving || (!on && (!phone || phoneDirty))}>
            <span aria-hidden="true" />
          </button>
        </div>
        {phoneDirty && phone ? <p className="profile-hint">Save your new number first. A new number needs a fresh opt-in.</p> : null}
        {showOptIn ? <div className="alerts-optin">
          <div className="profile-pair">
            <label className="profile-field"><span>First name</span><input value={first} onChange={e => setFirst(e.target.value)} maxLength={80} autoComplete="given-name" disabled={saving} /></label>
            <label className="profile-field"><span>Last name</span><input value={last} onChange={e => setLast(e.target.value)} maxLength={80} autoComplete="family-name" disabled={saving} /></label>
          </div>
          <label className="profile-check"><input type="checkbox" checked={consentValid && !phoneDirty} onChange={e => {setConsent(e.target.checked); setConsentPhone(phone);}} disabled={saving || phoneDirty || !phone} /> I want to receive Cues demo notifications</label>
          <div className="profile-actions">
            <button type="button" className="ws-pill" onClick={() => setAsking(false)} disabled={saving}>Cancel</button>
            <button type="button" className="ws-pill is-dark" onClick={() => void submit(true)} disabled={loading || saving || profileSaving || phoneDirty || !phone || !consentValid || !first.trim() || !last.trim()}>{saving ? "Saving…" : "Enable notifications"}</button>
          </div>
        </div> : null}
        {retry && !showOptIn ? <div className="alerts-foot">
          <button type="button" className="text-link" onClick={() => setAsking(true)} disabled={loading || saving || profileSaving}>Try again</button>
        </div> : null}
        {canTest ? <div className="alerts-foot">
          <button type="button" className="text-link" onClick={() => void testNotification()} disabled={loading || saving || profileSaving}>Send test notification</button>
          {testMessage ? <p className="profile-hint" role="status">{testMessage}</p> : null}
        </div> : null}
      </>}
      {error ? <div className="alerts-foot"><p className="profile-error" role="alert">{error}</p><button type="button" className="text-link" disabled={saving} onClick={() => setReload(n => n + 1)}>Try again</button></div> : null}
    </div>
  </section>;
}
