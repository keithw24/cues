import { priorityLabels } from "@/lib/teacher-reviews";

// Row contents shared by the dashboard and the landing page demo, so the demo
// shows the same rows teachers see. The caller owns the button and its state.
export type PersonTone = "working" | "done" | "review" | "quiet";

// "Person 3" → "P3"; any other name → its first letter.
export const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((word) => (/^\d+$/.test(word) ? word : word[0]))
    .join("")
    .slice(0, 3)
    .toUpperCase();

/** A person: who, their task, and their status as a labelled pill. Color
 * supports the label; it never carries the status alone. */
export function PersonRowContent({
  name,
  status,
  tone,
  activity,
}: {
  name: string;
  status: string;
  tone: PersonTone;
  activity: string;
}) {
  return (
    <>
      <span className="row-avatar" aria-hidden="true">
        {initials(name)}
      </span>
      <span className="row-body">
        <span className="row-name">{name}</span>
        {activity ? <span className="row-caption">{activity}</span> : null}
      </span>
      <span className={`status-pill is-${tone}`}>{status}</span>
    </>
  );
}

export function ReviewRowContent({
  name,
  meta,
  time,
  timeLabel,
  elevated,
}: {
  name: string;
  meta: string;
  time: string;
  /** A fixed label, so server and browser render the same text. */
  timeLabel?: string;
  elevated: boolean;
}) {
  return (
    <>
      <span className="row-avatar is-review" aria-hidden="true">
        {initials(name)}
      </span>
      <span className="row-body">
        <span className="row-name">{name}</span>
        {meta ? <span className="row-caption">{meta}</span> : null}
      </span>
      <span className="row-end">
        {elevated ? (
          <span className="status-pill is-review">
            Urgent
            <span className="sr-only"> ({priorityLabels.elevated})</span>
          </span>
        ) : null}
        <time className="row-time" dateTime={time}>
          {timeLabel ??
            new Intl.DateTimeFormat(undefined, {
              hour: "numeric",
              minute: "2-digit",
            }).format(new Date(time))}
        </time>
      </span>
    </>
  );
}
