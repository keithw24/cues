/** "Who needs you next": read from the review queue and seat statuses as the
 * backend reports them. Nothing is scored or ranked here beyond the queue's
 * own priority order. */
export type NextUp =
  | {
      kind: "review";
      name: string;
      detail: string;
      elevated: boolean;
      then: string[];
    }
  | { kind: "status"; name: string; detail: string; then: string[] }
  | { kind: "calm"; message: string };

export type NextUpReview = {
  name: string;
  activity: string;
  count: number;
  elevated: boolean;
};
export type NextUpPerson = { name: string; activity: string };

export function nextUp({
  reviews,
  flagged,
  inView,
  cameraReporting,
}: {
  /** Review groups, already in queue order (elevated first, then oldest). */
  reviews: readonly NextUpReview[];
  /** People whose current status is Needs Review. */
  flagged: readonly NextUpPerson[];
  inView: number;
  cameraReporting: boolean;
}): NextUp {
  const names = [
    ...reviews.map((review) => review.name),
    ...flagged
      .map((person) => person.name)
      .filter((name) => !reviews.some((review) => review.name === name)),
  ];
  const then = names.slice(1, 4);
  const [lead] = reviews;
  if (lead)
    return {
      kind: "review",
      name: lead.name,
      detail:
        lead.count > 1
          ? `${lead.activity} · ${lead.count} reviews waiting`
          : `${lead.activity} · a review is waiting`,
      elevated: lead.elevated,
      then,
    };
  const [person] = flagged;
  if (person)
    return {
      kind: "status",
      name: person.name,
      detail: `${person.activity} · may need a hand`,
      then,
    };
  return {
    kind: "calm",
    message: inView
      ? "Everyone’s working. Nothing needs you right now."
      : cameraReporting
        ? "No one is in view right now."
        : "The camera is off. People appear here when your classroom camera sees them.",
  };
}
