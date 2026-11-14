import type { LiveStatus } from "./live-class.ts";
import { resolutionLabels } from "./teacher-reviews.ts";

/** The simulated class behind /live when web.live_data is off. Invented
 * names, fixed clock labels; nothing reads or writes Supabase. */
export type MockStudent = {
  id: string;
  name: string;
  status: LiveStatus;
  tries: number;
  note: string;
};

export const MOCK_STUDENTS: readonly MockStudent[] = [
  {
    id: "P1",
    name: "Maya",
    status: "finished",
    tries: 1,
    note: "Finished at 9:38",
  },
  {
    id: "P2",
    name: "Leo",
    status: "needs",
    tries: 3,
    note: "3 tries, no finish yet",
  },
  {
    id: "P3",
    name: "Ava",
    status: "finished",
    tries: 2,
    note: "Finished at 9:42",
  },
  {
    id: "P4",
    name: "Noah",
    status: "working",
    tries: 1,
    note: "Started at 9:40",
  },
];

export const MOCK_LABELS: Record<LiveStatus, string> = {
  finished: "Finished",
  needs: "Needs you",
  working: "Working",
  ready: "Ready",
  checking: resolutionLabels.confirmed,
  quiet: "In view",
};

export const MOCK_FEED = [
  { id: "f5", text: "Leo flagged · 3 tries", time: "9:43" },
  { id: "f4", text: "Ava finished", time: "9:42" },
  { id: "f3", text: "Noah started", time: "9:40" },
  { id: "f2", text: "Maya finished", time: "9:38" },
  { id: "f1", text: "Raise your hand started", time: "9:31" },
] as const;

/** The headline for the simulated class: "2 of 4 finished", who needs you. */
export function mockSummary(students: readonly MockStudent[]) {
  return {
    finished: students.filter((s) => s.status === "finished").length,
    total: students.length,
    needs: students.filter((s) => s.status === "needs").length,
    working: students.filter(
      (s) => s.status === "working" || s.status === "checking",
    ).length,
  };
}
