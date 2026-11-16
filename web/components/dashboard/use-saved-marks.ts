import { useEffect, useState } from "react";
import { readMarked, writeMarked } from "@/lib/classroom-view";

/** The people the teacher marked as reviewed, kept in this tab's storage per classroom. */
export function useSavedMarks(station: string) {
  const [markedSeats, setMarkedSeats] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  // Marks are shared with the other page through this tab's storage, per
  // classroom, so a person marked on To review is not offered again (or named
  // in Attention) on the classroom page while the camera catches up.
  // Write only once this classroom's saved marks are in memory, so neither a
  // station switch nor a re-run effect (Strict Mode) writes the wrong set.
  const [marksLoadedFor, setMarksLoadedFor] = useState("");
  useEffect(() => {
    if (!station) return;
    let saved: string[] = [];
    try {
      saved = readMarked(window.sessionStorage, station);
    } catch {}
    queueMicrotask(() => {
      setMarkedSeats(new Set(saved));
      setMarksLoadedFor(station);
    });
  }, [station]);
  useEffect(() => {
    if (!station || marksLoadedFor !== station) return;
    try {
      writeMarked(window.sessionStorage, station, markedSeats);
    } catch {}
  }, [station, marksLoadedFor, markedSeats]);
  return [markedSeats, setMarkedSeats] as const;
}

/** A mark lasts until vision reports the person out of review: drop the marks of anyone no
 * longer flagged. `stillFlagged` is the comma-joined ids still flagged, null until seats load. */
export function useDropClearedMarks(
  stillFlagged: string | null,
  setMarkedSeats: React.Dispatch<React.SetStateAction<ReadonlySet<string>>>,
) {
  useEffect(() => {
    if (stillFlagged === null) return;
    const keep = new Set(stillFlagged ? stillFlagged.split(",") : []);
    queueMicrotask(() =>
      setMarkedSeats((previous) =>
        [...previous].every((id) => keep.has(id))
          ? previous
          : new Set([...previous].filter((id) => keep.has(id))),
      ),
    );
  }, [stillFlagged, setMarkedSeats]);
}
