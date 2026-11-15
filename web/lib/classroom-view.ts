/** What the classroom's student row and the To review cards show, as pure
 * functions so they are tested without rendering. Statuses come from the
 * backend; nothing here scores or ranks a student. */

export type StripTone = "working" | "done" | "review" | "quiet";

/** The word on a student's own card while Cues has asked the teacher about
 * them. It names the teacher's queue ("check in"), never the student's state:
 * "attention" is the teacher's panel, not a claim about the child. */
export const CHECK_IN_LABEL = "Check in";

export type StripSource = {
  id: string;
  name: string;
  /** The status label from the observation, e.g. "Working". */
  label: string;
  tone: StripTone;
  activity: string;
};

export type StripEntry = StripSource & { status: string; selected: boolean };

/**
 * One card per person the camera sees, in the order given (left to right in
 * the frame). Anyone with a pending request reads "Check in" in the review
 * tone; everyone else keeps their own status. The activity shows only when
 * the class is on more than one.
 */
export function stripEntries(
  inView: readonly StripSource[],
  waiting: ReadonlySet<string>,
  selectedId: string | null,
  mixedActivities: boolean,
): StripEntry[] {
  return inView.map((person) => {
    const asked = waiting.has(person.id);
    return {
      ...person,
      status: asked ? CHECK_IN_LABEL : person.label,
      tone: asked ? "review" : person.tone,
      activity: mixedActivities ? person.activity : "",
      selected: selectedId === person.id,
    };
  });
}

/** The line under a name on a To review card, e.g. "Raise hand · not in
 * view · 2 requests". */
export function reviewIssueLine(
  activity: string,
  visible: boolean,
  count: number,
): string {
  return [
    activity,
    visible ? null : "not in view",
    count > 1 ? `${count} requests` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * People the camera has flagged (their row reads Needs Review) who have no
 * pending request from Cues yet, in the order given (web.review_waiting). The
 * agent may still be deciding, or its call may have failed; either way the
 * teacher sees them. Someone already marked reviewed is left out until vision
 * moves them back to working.
 */
export function flaggedWithoutRequest<T extends { id: string }>(
  people: readonly T[],
  flagged: (person: T) => boolean,
  asked: ReadonlySet<string>,
  marked: ReadonlySet<string>,
): T[] {
  return people.filter(
    (person) => flagged(person) && !asked.has(person.id) && !marked.has(person.id),
  );
}

/**
 * What To review counts and lists beyond Cues's requests. Off, or while the
 * review feed is not live, it is exactly as before: no extra people, and the
 * count is the number of people with requests (0 until the feed is live).
 */
export function reviewQueue<T extends { id: string }>({
  enabled,
  live,
  people,
  flagged,
  askedSeatIds,
  marked,
}: {
  enabled: boolean;
  live: boolean;
  people: readonly T[];
  flagged: (person: T) => boolean;
  askedSeatIds: readonly string[];
  marked: ReadonlySet<string>;
}): { flagged: T[]; count: number } {
  if (!live) return { flagged: [], count: 0 };
  const extra = enabled
    ? flaggedWithoutRequest(people, flagged, new Set(askedSeatIds), marked)
    : [];
  return { flagged: extra, count: askedSeatIds.length + extra.length };
}
