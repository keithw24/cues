// Runs one of the dashboard's real TypeScript parsers on JSON that Python produced.
//   node --experimental-strip-types tests/contract/ts_consumer.ts <kind> <file.json>
// Prints {"ok":true,...} or exits non-zero with the parser's own error.
import { readFileSync } from "node:fs";
import { parseSnapshot, statuses } from "../../web/lib/dashboard.ts";
import { parseSession, parseStationRuntime } from "../../web/lib/session-controls.ts";
import { evidenceLabels, parseTeacherReviews } from "../../web/lib/teacher-reviews.ts";
import { parseInsights } from "../../web/lib/insights.ts";
import { agentIsAlive, evaluatedProgress } from "../../web/lib/progress-context.ts";

const [kind, file, station] = process.argv.slice(2);
const data = JSON.parse(readFileSync(file, "utf8"));
const out = (value: object) => console.log(JSON.stringify({ ok: true, ...value }));

switch (kind) {
  case "vocabulary":
    out({ statuses: Object.keys(statuses), evidence: Object.keys(evidenceLabels) });
    break;
  case "snapshot": {
    const snapshot = parseSnapshot(data, true);
    out({ seats: snapshot.seats.length, states: snapshot.states.length });
    break;
  }
  case "session": {
    const session = parseSession(data.session, station);
    out({ id: session.id, revision: session.revision });
    break;
  }
  case "runtime": {
    const runtime = parseStationRuntime(data.station_runtime, station);
    out({ status: runtime?.status ?? null });
    break;
  }
  case "progress": {
    // What a dashboard row shows, exactly as the dashboard decides it.
    const row = parseSnapshot(
      { seats: [], states: [data.row], activities: [], stations: [] },
      true,
    ).states[0];
    const shown = evaluatedProgress(row, data.now, agentIsAlive(data.agent_seen_at, data.now));
    out({ visible: shown !== null, trend: shown?.trend ?? null,
          stalled_since: shown?.stalled_since ?? null, recent: shown?.recent.length ?? 0 });
    break;
  }
  case "reviews":
    out({ reviews: parseTeacherReviews(data).length });
    break;
  case "insights": {
    const insights = parseInsights(data);
    out({ reviews: insights.totals.reviews_raised, supports: insights.supports.length });
    break;
  }
  default:
    throw new Error(`unknown kind ${kind}`);
}
