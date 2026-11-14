"use client";

import { useState } from "react";
import {
  LiveCameraLink,
  LiveCard,
  LiveClass,
  LiveFeed,
  LiveHero,
} from "@/components/live-screen";
import { resolutionLabels, reviewPrompt } from "@/lib/teacher-reviews";
import type { LiveStatus } from "@/lib/live-class";
import {
  MOCK_FEED,
  MOCK_LABELS,
  MOCK_STUDENTS,
  mockSummary,
} from "@/lib/live-mock-data";

// A design mock of the Live screen with a simulated class. Nothing here reads
// or writes Supabase; the data lives in lib/live-mock-data.ts.
// Minutes after 9:00 → a clock label.
const clock = (minutes: number) => {
  const total = 9 * 60 + Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")}`;
};

export default function LiveMock() {
  const [students, setStudents] = useState([...MOCK_STUDENTS]);
  // The teacher decides on the model's review, as on the dashboard:
  // Support needed (confirmed) or No support needed (dismissed).
  const [card, setCard] = useState<"ask" | "confirmed" | "dismissed" | "done">(
    "ask",
  );

  const { finished, total, needs, working } = mockSummary(students);
  const setLeo = (status: LiveStatus, note: string) =>
    setStudents((list) =>
      list.map((s) => (s.id === "P2" ? { ...s, status, note } : s)),
    );

  return (
    <div className="live">
      <div className="live-main-col">
        <LiveHero
          activity="Raise your hand"
          simulated
          count={finished}
          total={total}
          noun="finished"
          summary={
            <>
              {needs ? (
                <span className="live-up">{needs} needs you</span>
              ) : (
                <span>No one waiting</span>
              )}
              <span>
                {" "}
                · {working} working · now {clock(44)}
              </span>
            </>
          }
        />

        <LiveCard>
          {card === "ask" ? (
            <>
              <div className="live-card-who">
                <span className="live-avatar is-needs" aria-hidden="true">
                  L
                </span>
                <div>
                  <p className="live-card-title">Leo may need support</p>
                  <p className="live-card-note">Raise your hand · 9:43</p>
                </div>
              </div>
              <p className="live-card-rationale">{reviewPrompt.detail}</p>
              <p className="live-card-note">
                Cues: Repeated stalled progress on this task. Based on current
                task progress, previous prompts.
              </p>
              <div className="live-card-actions">
                <button
                  type="button"
                  className="live-btn is-primary"
                  onClick={() => {
                    setCard("confirmed");
                    setLeo("checking", "You decided support is needed");
                  }}
                >
                  {resolutionLabels.confirmed}
                </button>
                <button
                  type="button"
                  className="live-btn"
                  onClick={() => {
                    setCard("dismissed");
                    setLeo("working", "You decided no support is needed");
                  }}
                >
                  {resolutionLabels.dismissed}
                </button>
              </div>
            </>
          ) : card === "done" ? (
            <>
              <p className="live-card-title">Everyone’s working</p>
              <p className="live-card-note">Nothing needs you right now.</p>
            </>
          ) : (
            <>
              <p className="live-card-title">
                Leo: {resolutionLabels[card].toLowerCase()}
              </p>
              <p className="live-card-note">
                Simulated class: nothing is saved.
              </p>
              <div className="live-card-actions">
                <button
                  type="button"
                  className="live-btn"
                  onClick={() => setCard("done")}
                >
                  Done
                </button>
              </div>
            </>
          )}
        </LiveCard>

        <LiveFeed
          title="This lesson"
          items={[...MOCK_FEED]}
          empty="Nothing yet."
        />
      </div>

      <LiveClass
        students={students.map((student) => ({
          ...student,
          label: MOCK_LABELS[student.status],
          details: [
            student.note,
            `Raise your hand · position ${student.id.slice(1)} from the left`,
          ],
        }))}
        empty="No one in view."
        action={<LiveCameraLink />}
      />
    </div>
  );
}
