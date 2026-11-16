import { useEffect, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { cameraConflict, readStationWriter } from "@/lib/station-writer";

/** True while another camera holds this station and this one is refused (and paused). */
export function useCameraConflict(
  client: SupabaseClient | null,
  station: string,
) {
  const [conflict, setConflict] = useState(false);
  useEffect(() => {
    if (!client || !station) return;
    let disposed = false;
    // One read at a time (a read can take up to 12s, the poll is 5s), so an
    // old answer never overwrites a newer one; a failed read keeps the last.
    let inFlight = false;
    // The last writer read; while reads fail it is re-checked against the
    // clock, so the warning still expires once the other camera goes quiet.
    let lastWriter: Awaited<ReturnType<typeof readStationWriter>> | null = null;
    const check = () => {
      if (lastWriter && !disposed)
        setConflict(cameraConflict(lastWriter, Date.now()));
      if (inFlight) return;
      inFlight = true;
      void readStationWriter(client, station)
        .then((writer) => {
          lastWriter = writer;
          if (!disposed) setConflict(cameraConflict(writer, Date.now()));
        })
        .catch(() => {})
        .finally(() => {
          inFlight = false;
        });
    };
    check();
    const timer = setInterval(check, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
      // Never carry one classroom's warning over to the next.
      setConflict(false);
    };
  }, [client, station]);
  return conflict;
}
