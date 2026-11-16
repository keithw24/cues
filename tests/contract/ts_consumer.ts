// Runs one of the dashboard's real TypeScript parsers on JSON that Python produced.
//   node --experimental-strip-types tests/contract/ts_consumer.ts <kind> <file.json>
// Prints {"ok":true,...} or exits non-zero with the parser's own error.
import { readFileSync } from "node:fs";
import { parseSnapshot, statuses } from "../../web/lib/dashboard.ts";
import { parseSession, parseStationRuntime } from "../../web/lib/session-controls.ts";
import { parseTeacherReviews } from "../../web/lib/teacher-reviews.ts";

const [kind, file, station] = process.argv.slice(2);
const data = JSON.parse(readFileSync(file, "utf8"));
const out = (value: object) => console.log(JSON.stringify({ ok: true, ...value }));

switch (kind) {
  case "vocabulary":
    out({ statuses: Object.keys(statuses) });
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
  case "reviews":
    out({ reviews: parseTeacherReviews(data).length });
    break;
  default:
    throw new Error(`unknown kind ${kind}`);
}
