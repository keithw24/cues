"use client";

import Link from "next/link";
import { useState } from "react";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { useInsights } from "@/components/insights/use-insights";
import { INTERVENTION_MENU } from "@/lib/interventions";
import { evidenceLabels, type EvidenceSource } from "@/lib/teacher-reviews";
import type { Insights } from "@/lib/insights";
import {
  MIN_CASES,
  RANGES,
  classTime,
  clockDuration,
  fillWeeks,
  heatGrid,
  hourLabel,
  perHour,
  weekLabel,
} from "@/lib/insights-view";

const percent = (part: number, whole: number) =>
  whole ? Math.round((part / whole) * 100) : 0;

function Kpi({
  value,
  unit,
  caption,
  detail,
  good,
}: {
  value: string;
  unit?: string;
  caption: string;
  detail: string;
  good?: boolean;
}) {
  return (
    <div className="ins-kpi">
      <p className="ins-kpi-number">
        {value}
        {unit ? <small>{unit}</small> : null}
      </p>
      <p className="ins-caption">{caption}</p>
      <p className={`ins-detail${good ? " is-good" : ""}`}>{detail}</p>
    </div>
  );
}

function Glance({ data }: { data: Insights }) {
  const { totals, previous } = data;
  const change = totals.reviews_raised - previous.reviews_raised;
  const compare = !previous.sessions
    ? "Nothing earlier to compare"
    : change === 0
      ? "Same as the period before"
      : `${change < 0 ? "↓" : "↑"} ${Math.abs(change)} vs the period before`;
  return (
    <section className="ins-kpis" aria-label="At a glance">
      <Kpi
        value={String(totals.sessions)}
        caption="Sessions"
        detail={`${classTime(totals.class_seconds)} of class time`}
      />
      <Kpi
        value={String(totals.reviews_raised)}
        caption="Check-ins Cues asked for"
        detail={compare}
        good={previous.sessions > 0 && change < 0}
      />
      <Kpi
        value={String(percent(totals.approved_supports, totals.reviews_raised))}
        unit="%"
        caption="You approved a support"
        detail={`${totals.approved_supports} of ${totals.reviews_raised} check-ins`}
      />
      <Kpi
        value={clockDuration(totals.median_decision_seconds)}
        caption="Median time to answer"
        detail="from request to your decision"
      />
    </section>
  );
}

function WeeklyBars({ data }: { data: Insights }) {
  const weeks = fillWeeks(data.weekly);
  const max = Math.max(1, ...weeks.flatMap((w) => [w.sessions, w.reviews_raised]));
  return (
    <section className="ins-card ins-wide" aria-labelledby="ins-week">
      <h2 id="ins-week">What happened, week by week</h2>
      <p className="ins-hint">Sessions run and check-ins Cues asked for</p>
      {weeks.length ? (
        <>
          <div className="ins-bars" role="list">
            {weeks.map((w) => (
              <div
                key={w.week_start}
                role="listitem"
                aria-label={`Week of ${weekLabel(w.week_start)}: ${w.sessions} sessions, ${w.reviews_raised} check-ins`}
              >
                <i className="is-sessions" style={{ height: `${(w.sessions / max) * 100}%` }} />
                <i className="is-asked" style={{ height: `${(w.reviews_raised / max) * 100}%` }} />
              </div>
            ))}
          </div>
          <div className="ins-axis" aria-hidden="true">
            {weeks.map((w) => (
              <span key={w.week_start}>{weekLabel(w.week_start)}</span>
            ))}
          </div>
          <p className="ins-legend">
            <span><b className="is-sessions" />Sessions</span>
            <span><b className="is-asked" />Check-ins asked</span>
          </p>
        </>
      ) : (
        <p className="ins-empty">No sessions in this period.</p>
      )}
    </section>
  );
}

function WhyAsked({ data }: { data: Insights }) {
  const entries = (Object.entries(data.evidence) as [EvidenceSource, number][]).sort(
    (a, b) => b[1] - a[1],
  );
  const raised = data.totals.reviews_raised;
  return (
    <section className="ins-card" aria-labelledby="ins-why">
      <h2 id="ins-why">Why Cues asked</h2>
      <p className="ins-hint">What the agent looked at when it asked</p>
      {entries.length ? (
        <ul className="ins-rows">
          {entries.map(([source, uses]) => (
            <li key={source}>
              <span>{evidenceLabels[source]}</span>
              <span className="ins-track">
                <i style={{ width: `${percent(uses, raised)}%` }} />
              </span>
              <span className="ins-value">{uses}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ins-empty">No check-ins in this period.</p>
      )}
      <p className="ins-hint ins-foot">
        Every check-in starts from no progress for a while. Facial expression is never the reason.
      </p>
    </section>
  );
}

function Outcomes({ data }: { data: Insights }) {
  const t = data.totals;
  const parts = [
    { key: "confirmed", label: "Approved a support", n: t.confirmed },
    { key: "dismissed", label: "Not needed", n: t.dismissed },
    { key: "reviewed", label: "Marked reviewed", n: t.reviewed },
    { key: "expired", label: "Finished on their own", n: t.expired },
    { key: "pending", label: "Still waiting", n: t.pending },
  ];
  return (
    <section className="ins-card" aria-labelledby="ins-answers">
      <h2 id="ins-answers">Your answers</h2>
      <p className="ins-hint">
        {t.reviews_raised} check-in{t.reviews_raised === 1 ? "" : "s"}, how each one ended
      </p>
      {t.reviews_raised ? (
        <div className="ins-stack" role="img"
          aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(", ")}>
          {parts.filter((p) => p.n).map((p) => (
            <i key={p.key} className={`is-${p.key}`} style={{ flexGrow: p.n }} />
          ))}
        </div>
      ) : null}
      <ul className="ins-keys">
        {parts.map((p) => (
          <li key={p.key}>
            <span><b className={`is-${p.key}`} />{p.label}</span>
            <em>{p.n}</em>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Supports({ data }: { data: Insights }) {
  return (
    <section className="ins-card ins-wide" aria-labelledby="ins-supports">
      <h2 id="ins-supports">Supports you approved</h2>
      <p className="ins-hint">And whether progress picked up within 5 minutes</p>
      {data.supports.length ? (
        <table className="ins-table">
          <thead>
            <tr>
              <th scope="col">Support</th>
              <th scope="col" className="is-num">Approved</th>
              <th scope="col" className="is-num">Progress resumed</th>
            </tr>
          </thead>
          <tbody>
            {data.supports.map((s) => {
              const enough = s.approved >= MIN_CASES;
              return (
                <tr key={s.action}>
                  <th scope="row">{INTERVENTION_MENU[s.action]}</th>
                  <td className="is-num">{s.approved}</td>
                  <td className="is-num">
                    <span
                      className={`ins-chip${!enough ? " is-quiet" : s.resumed / s.approved >= 0.6 ? " is-good" : " is-warn"}`}
                    >
                      {enough ? `${s.resumed} of ${s.approved}` : "too few"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="ins-empty">No supports approved in this period.</p>
      )}
    </section>
  );
}

function Activities({ data }: { data: Insights }) {
  const rows = data.activities.map((a) => ({
    ...a,
    rate: perHour(a.reviews_raised, a.class_seconds),
  }));
  const max = Math.max(0.1, ...rows.map((r) => r.rate ?? 0));
  return (
    <section className="ins-card" aria-labelledby="ins-activities">
      <h2 id="ins-activities">Which activities</h2>
      <p className="ins-hint">Check-ins per hour of class time</p>
      {rows.length ? (
        <ul className="ins-rows">
          {rows.map((r) => (
            <li key={r.activity_id}>
              <span>{r.name}</span>
              <span className="ins-track">
                <i style={{ width: `${((r.rate ?? 0) / max) * 100}%` }} />
              </span>
              <span className="ins-value">
                {r.rate === null ? `${r.reviews_raised}` : r.rate.toFixed(1)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ins-empty">No activity in this period.</p>
      )}
      {rows.some((r) => r.rate === null) ? (
        <p className="ins-hint ins-foot">
          A plain number is a count: under 10 minutes of class time is too little for a rate.
        </p>
      ) : null}
    </section>
  );
}

function Heat({ data }: { data: Insights }) {
  const grid = heatGrid(data.heat);
  return (
    <section className="ins-card ins-wide" aria-labelledby="ins-when">
      <h2 id="ins-when">When it happens</h2>
      <p className="ins-hint">Check-ins by weekday and hour, in your time zone</p>
      {grid ? (
        <div
          className="ins-heat"
          role="table"
          aria-label="Check-ins by weekday and hour"
          style={{ gridTemplateColumns: `36px repeat(${grid.hours.length}, 1fr)` }}
        >
          <span role="row" className="ins-heat-head">
            <span />
            {grid.hours.map((h) => (
              <span key={h} role="columnheader" aria-label={hourLabel(h)}>
                {grid.hours.length <= 12 || h % 3 === 0 ? hourLabel(h) : ""}
              </span>
            ))}
          </span>
          {grid.days.map(({ dow, label }) => (
            <span role="row" className="ins-heat-row" key={dow}>
              <span role="rowheader">{label}</span>
              {grid.hours.map((h) => {
                const n = grid.count(dow, h);
                return (
                  <i
                    key={h}
                    role="cell"
                    title={`${label} ${hourLabel(h)}:00, ${n} check-in${n === 1 ? "" : "s"}`}
                    aria-label={`${n}`}
                    style={{ opacity: n ? 0.18 + 0.82 * (n / grid.max) : 0.06 }}
                  />
                );
              })}
            </span>
          ))}
        </div>
      ) : (
        <p className="ins-empty">No check-ins in this period.</p>
      )}
    </section>
  );
}

export default function InsightsPage() {
  const [days, setDays] = useState<number>(30);
  const [activity, setActivity] = useState<string | null>(null);
  const { configured, auth, activities, loading, data, error, retry } = useInsights(days, activity);
  const signedOut = auth === "signed-out";

  return (
    <div className="dashboard-shell">
      <WorkspaceSidebar />
      <main id="main-content" className="dashboard-main">
        {signedOut ? (
          <section className="ws-signin" aria-labelledby="ins-signin">
            <h1 id="ins-signin">Sign in to see your insights</h1>
            <p>Cues rolls up your finished sessions so you can see what happened and why.</p>
            <Link className="ws-pill is-dark" href="/login">
              Sign in
              <WorkspaceIcon name="arrow" />
            </Link>
          </section>
        ) : (
          <section className="ws-hero" aria-labelledby="ins-heading">
            <header className="page-intro">
              <div>
                <h1 id="ins-heading">insights</h1>
                <p className="ws-subtitle">What happened across your sessions, and why Cues asked</p>
              </div>
              <Link className="ws-pill" href="/dashboard">
                <WorkspaceIcon name="back" />
                Back to classroom
              </Link>
            </header>

            <div className="session-controls">
              <div className="session-row">
                {RANGES.map((r) => (
                  <button
                    key={r.days}
                    type="button"
                    className={`ws-pill${days === r.days ? " is-dark" : ""}`}
                    aria-pressed={days === r.days}
                    onClick={() => setDays(r.days)}
                  >
                    {r.label}
                  </button>
                ))}
                <select
                  aria-label="Activity"
                  value={activity ?? ""}
                  onChange={(event) => setActivity(event.target.value || null)}
                >
                  <option value="">All activities</option>
                  {activities.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {!configured ? (
              <p className="ins-empty" role="alert">
                Insights aren’t available: the dashboard connection isn’t set up.
              </p>
            ) : error ? (
              <div className="ins-empty" role="alert">
                <p>{error}</p>
                <button type="button" className="ws-pill" onClick={retry}>Try again</button>
              </div>
            ) : !data ? (
              <p className="ins-empty" role="status">
                {auth === "checking" || loading ? "Loading…" : null}
              </p>
            ) : data.totals.sessions === 0 ? (
              <p className="ins-empty" role="status">
                No finished sessions in this period yet. Insights appear once a session ends.
              </p>
            ) : (
              <div className="ins-body" aria-busy={loading}>
                <Glance data={data} />
                <div className="ins-grid is-wide"><WeeklyBars data={data} /><WhyAsked data={data} /></div>
                <p className="list-label">What you decided</p>
                <div className="ins-grid is-even"><Outcomes data={data} /><Supports data={data} /></div>
                <p className="list-label">Where and when</p>
                <div className="ins-grid is-even"><Activities data={data} /><Heat data={data} /></div>
                <p className="ins-footnote">
                  Counts for the classroom, not scores for children. Cues does not detect emotion
                  or attention, and nothing here is a grade or a diagnosis. Camera images never
                  leave your laptop.
                </p>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
