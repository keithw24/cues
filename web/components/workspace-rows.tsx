import type { ComponentProps } from "react";
import { WorkspaceIcon } from "@/components/workspace-icon";
import { priorityLabels } from "@/lib/teacher-reviews";

// Row contents shared by the dashboard and the landing page demo, so the demo
// shows the same rows teachers see. The caller owns the button and its state.
type IconName = ComponentProps<typeof WorkspaceIcon>["name"];

// "Person 3" → "P3"; a made-up simulated name → its first letter.
export const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((word) => (/^\d+$/.test(word) ? word : word[0]))
    .join("")
    .slice(0, 3)
    .toUpperCase();

export function PersonRowContent({
  name,
  status,
  icon,
  activity,
}: {
  name: string;
  status: string;
  icon: IconName;
  activity: string;
}) {
  return (
    <>
      <span className="seat-avatar" aria-hidden="true">
        {initials(name)}
      </span>
      <span className="seat-item-body">
        <span className="seat-item-name">{name}</span>
        <span className="seat-item-meta">
          <span className="seat-item-status">
            <WorkspaceIcon name={icon} />
            {status}
          </span>
          <span className="seat-item-activity">{activity}</span>
        </span>
      </span>
      <WorkspaceIcon className="seat-item-arrow" name="chevronRight" />
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
      <span className="seat-avatar" aria-hidden="true">
        {initials(name)}
      </span>
      <span className="review-body">
        <span className="review-name">{name}</span>
        <span className="review-meta">{meta}</span>
      </span>
      <time className="review-time" dateTime={time}>
        {timeLabel ??
          new Intl.DateTimeFormat(undefined, {
            hour: "numeric",
            minute: "2-digit",
          }).format(new Date(time))}
      </time>
      {elevated ? (
        <span className="review-flag">
          <WorkspaceIcon name="flag" />
          <span className="sr-only">{priorityLabels.elevated}</span>
        </span>
      ) : null}
    </>
  );
}
