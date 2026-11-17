import type { Insights } from "./insights.ts";

/** Below this many cases a rate says too little to show. */
export const MIN_CASES = 3;
/** Check-ins per hour is shown only for activities with at least this much class time. */
export const MIN_RATE_SECONDS = 600;

export const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
] as const;

/** "1:40" for 100 seconds, "12:05" for 725. */
export function clockDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

/** "11 h 40 m", "25 m", "0 m". */
export function classTime(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} m` : `${minutes} m`;
}

/** Check-ins per hour of class time, or null when there is too little time to say. */
export function perHour(reviews: number, seconds: number): number | null {
  return seconds < MIN_RATE_SECONDS ? null : (reviews * 3600) / seconds;
}

const DAY = 86_400_000;
const parseDay = (day: string) => Date.parse(`${day}T00:00:00Z`);
const formatDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** Every week from the first to the last with data, empty weeks as zeros, so gaps show. */
export function fillWeeks(weekly: Insights["weekly"]): Insights["weekly"] {
  if (!weekly.length) return [];
  const byWeek = new Map(weekly.map((w) => [w.week_start, w]));
  const first = parseDay(weekly[0].week_start);
  const last = parseDay(weekly[weekly.length - 1].week_start);
  const out: Insights["weekly"] = [];
  for (let at = first; at <= last; at += 7 * DAY) {
    const day = formatDay(at);
    out.push(byWeek.get(day) ?? { week_start: day, sessions: 0, reviews_raised: 0 });
  }
  return out;
}

export const WEEKDAYS = [
  { dow: 1, label: "Mon" },
  { dow: 2, label: "Tue" },
  { dow: 3, label: "Wed" },
  { dow: 4, label: "Thu" },
  { dow: 5, label: "Fri" },
  { dow: 6, label: "Sat" },
  { dow: 0, label: "Sun" },
] as const;

/** The weekday-by-hour grid: only the hours that matter (at least 6), only weekend days with data. */
export function heatGrid(heat: Insights["heat"]) {
  if (!heat.length) return null;
  const hours = heat.map((h) => h.hour);
  let from = Math.min(...hours);
  let to = Math.max(...hours);
  while (to - from < 5) {
    if (from > 0) from -= 1;
    if (to - from < 5 && to < 23) to += 1;
    if (from === 0 && to === 23) break;
  }
  const counts = new Map(heat.map((h) => [`${h.dow}-${h.hour}`, h.count]));
  const max = Math.max(...heat.map((h) => h.count));
  const days = WEEKDAYS.filter(
    ({ dow }) => dow >= 1 && dow <= 5 || heat.some((h) => h.dow === dow),
  );
  return {
    hours: Array.from({ length: to - from + 1 }, (_, i) => from + i),
    days,
    count: (dow: number, hour: number) => counts.get(`${dow}-${hour}`) ?? 0,
    max,
  };
}

/** "9a", "12p", "3p": the hour as a teacher reads a clock. */
export const hourLabel = (hour: number) =>
  `${hour % 12 === 0 ? 12 : hour % 12}${hour < 12 ? "a" : "p"}`;

/** "Sep 22" for a week_start date. */
export function weekLabel(day: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${day}T00:00:00Z`));
}
