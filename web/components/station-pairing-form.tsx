"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createDashboardClient } from "@/lib/supabase";
import { readStationMemberships, redeemStationCode, StationSignInRequired } from "@/lib/station-pairing";
import "./teacher-profile.css";

export default function StationPairingForm() {
  const [client] = useState(() => { try { return createDashboardClient(true); } catch { return null; } });
  const [memberships, setMemberships] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [state, setState] = useState("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const locked = useRef(false);
  const epoch = useRef(0);
  useEffect(() => {
    if (!client) return;
    let disposed = false;
    const invalidate = () => { epoch.current++; };
    async function load() {
      const current = ++epoch.current;
      setState("loading"); setMemberships([]); setMessage(null); setCode("");
      try {
        const rows = await readStationMemberships(client!);
        if (!disposed && current === epoch.current) { setMemberships(rows); setState("ready"); }
      } catch (error) {
        if (!disposed && current === epoch.current) {
          setState(error instanceof StationSignInRequired ? "signed-out" : "error");
          setMessage(error instanceof Error ? error.message : "Camera links are unavailable.");
        }
      }
    }
    void load();
    // Defer Supabase calls outside its auth callback to avoid auth lock contention.
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const { data } = client.auth.onAuthStateChange(() => {
      invalidate();
      const timer = setTimeout(() => { timers.delete(timer); if (!disposed) void load(); }, 0);
      timers.add(timer);
    });
    return () => { disposed = true; invalidate(); timers.forEach(clearTimeout); data.subscription.unsubscribe(); };
  }, [client, retry]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!client || locked.current || state !== "ready" || !code.trim()) return;
    locked.current = true; setState("saving"); setMessage(null);
    const current = epoch.current;
    try {
      const station = await redeemStationCode(client, code);
      if (current !== epoch.current) return;
      setMemberships(previous => [...new Set([...previous, station])].sort());
      setMessage(`Linked to camera ${station}`); setCode(""); setState("ready");
    } catch (error) {
      if (current !== epoch.current) return;
      setState(error instanceof StationSignInRequired ? "signed-out" : "ready");
      setMessage(error instanceof Error ? error.message : "Could not link the camera.");
    } finally { locked.current = false; }
  }
  if (!client) return <p role="alert">Teacher accounts are not configured in this environment.</p>;
  if (state === "signed-out") return <div className="integration-details"><p>Sign in to link a classroom camera.</p><Link href="/login">Teacher sign in</Link></div>;
  if (state === "loading") return <p role="status">Loading your cameras…</p>;
  if (state === "error") return <div className="integration-details"><p role="alert">{message}</p><button onClick={() => setRetry(value => value + 1)}>Retry</button></div>;
  return <form className="integration-details profile-form" onSubmit={submit} aria-busy={state === "saving"}>
    {memberships.length ? <section><h2>Linked cameras</h2><ul>{memberships.map(id => <li key={id}>{id}</li>)}</ul></section> : <p>No cameras linked yet.</p>}
    <label className="profile-field"><span>Pairing code</span><input value={code} onChange={event => setCode(event.target.value)} maxLength={128} autoComplete="off" spellCheck={false} disabled={state === "saving"} /></label>
    <button className="primary-button" type="submit" disabled={state === "saving" || !code.trim()}>{state === "saving" ? "Connecting…" : "Link camera"}</button>
    {message ? <p role="status" aria-live="polite">{message}</p> : null}
    <Link className="quiet-link" href="/dashboard">Back to classroom</Link>
  </form>;
}
