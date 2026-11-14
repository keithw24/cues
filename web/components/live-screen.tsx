"use client";

import { useState, type ReactNode } from "react";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { initials } from "@/components/workspace-rows";
import "./live.css";

// The Live screen's pieces: one big number, a card for whoever needs you, a short feed, and the
// class as a list with status pills.
import type { LiveStatus } from "@/lib/live-class";
export type { LiveStatus };
export type LiveStudent = {
  id: string;
  name: string;
  status: LiveStatus;
  label: string;
  tries?: number;
  details: string[];
};

export const clockTime = (ms: number) =>
  new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(ms));

export function LiveHero({
  activity,
  count,
  total,
  noun,
  summary,
}: {
  activity: string;
  count: ReactNode;
  total: number | null;
  noun: string;
  summary: ReactNode;
}) {
  return (
    <header className="live-hero">
      <p className="live-eyebrow">{activity}</p>
      <p className="live-big" aria-live="polite">
        {count}
        {total ? <span className="live-big-of"> of {total}</span> : null}{" "}
        <span className="live-big-noun">{noun}</span>
      </p>
      <p className="live-sub">{summary}</p>
    </header>
  );
}

export function LiveCard({ children }: { children: ReactNode }) {
  return (
    <section className="live-card" aria-live="polite">
      {children}
    </section>
  );
}

export function LiveFeed({
  title,
  items,
  empty,
}: {
  title: string;
  items: { id: string; text: string; time: string; dateTime?: string }[];
  empty: string;
}) {
  return (
    <section className="live-feed" aria-labelledby="feed-heading">
      <h2 id="feed-heading">{title}</h2>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <span>{item.text}</span>
              <time dateTime={item.dateTime}>{item.time}</time>
            </li>
          ))}
        </ul>
      ) : (
        <p className="live-feed-empty">{empty}</p>
      )}
    </section>
  );
}

export function LiveClass({
  students,
  empty,
  action,
}: {
  students: LiveStudent[];
  empty: string;
  action?: ReactNode;
}) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <aside className="live-side" aria-labelledby="class-heading">
      <div className="live-side-head">
        <h2 id="class-heading">Class</h2>
        <span>left to right</span>
      </div>
      {students.length ? (
        <ul className="live-list">
          {students.map((student) => (
            <li key={student.id}>
              <button
                type="button"
                className="live-row"
                aria-expanded={open === student.id}
                onClick={() => setOpen(open === student.id ? null : student.id)}
              >
                <span
                  className={`live-avatar is-${student.status}`}
                  aria-hidden="true"
                >
                  {initials(student.name)}
                </span>
                <span className="live-row-body">
                  <span className="live-row-name">{student.name}</span>
                  {student.tries ? (
                    <span
                      className="live-tries"
                      aria-label={`${student.tries} tries`}
                    >
                      {Array.from({ length: student.tries }, (_, i) => (
                        <i key={i} />
                      ))}
                    </span>
                  ) : null}
                </span>
                <span className={`live-pill is-${student.status}`}>
                  {student.label}
                </span>
              </button>
              <div
                className="live-row-more"
                data-open={open === student.id || undefined}
              >
                <div>
                  {student.details.map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="live-side-empty">{empty}</p>
      )}
      {action}
    </aside>
  );
}

export function LiveCameraLink() {
  return (
    <a className="live-btn is-wide live-btn-link" href="/dashboard">
      <WorkspaceIcon name="camera" />
      Camera and details
    </a>
  );
}
