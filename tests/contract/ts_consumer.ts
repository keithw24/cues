// Runs the dashboard's real TypeScript code on JSON that Python produced, and prints what the
// dashboard made of it.
//   node --experimental-strip-types tests/contract/ts_consumer.ts <kind> <file.json> [station]
// Prints {"ok":true,...} or exits non-zero with the parser's own error.
//
// Only modules that import nothing at run time (types are erased) are used, so this runs
// without `npm ci`: it is the same code the browser runs, not a copy of its rules.
import { readFileSync } from "node:fs";
import { parseSnapshot, statuses } from "../../web/lib/dashboard.ts";
import { parseSession, parseStationRuntime } from "../../web/lib/session-controls.ts";
import {
  REVIEW_COLUMNS_WITH_INTERVENTIONS,
  evidenceLabels,
  parseTeacherReviews,
} from "../../web/lib/teacher-reviews.ts";
import { parseInsights } from "../../web/lib/insights.ts";
import { agentIsAlive, evaluatedProgress } from "../../web/lib/progress-context.ts";
import { INTERVENTION_MENU } from "../../web/lib/interventions.ts";
import { E164, STATION_ID } from "../../web/lib/ids.ts";
import { configureLocalVision } from "../../web/lib/local-vision.ts";
import { readLocalVision } from "../../web/lib/camera-health.ts";

const [kind, file, station] = process.argv.slice(2);
const data = JSON.parse(readFileSync(file, "utf8"));
const out = (value: object) => console.log(JSON.stringify({ ok: true, ...value }));

// A fetch that answers from canned JSON, and remembers what it was sent.
const sent: { url: string; method: string; body: unknown }[] = [];
const canned = (answers: Record<string, unknown>, status = 200) =>
  (url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    sent.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(
      new Response(JSON.stringify(answers[path] ?? {}), {
        status,
        headers: { "content-type": "application/json" },
      }),
    );
  };

async function main() {
  switch (kind) {
    case "vocabulary":
      out({ statuses: Object.keys(statuses), evidence: Object.keys(evidenceLabels) });
      break;
    case "menu":
      out({
        menu: INTERVENTION_MENU,
        review_columns: REVIEW_COLUMNS_WITH_INTERVENTIONS.split(","),
      });
      break;
    case "ids":
      out({
        stations: (data.stations as string[]).map((s) => STATION_ID.test(s)),
        phones: (data.phones as string[]).map((s) => E164.test(s)),
      });
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
      out({
        visible: shown !== null,
        trend: shown?.trend ?? null,
        stalled_since: shown?.stalled_since ?? null,
        recent: shown?.recent.length ?? 0,
      });
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
    case "vision_read": {
      // The dashboard reading this laptop's vision service; the answers are canned.
      const reading = await readLocalVision(
        canned({ "/health": data.health, "/config": data.config }),
        "http://127.0.0.1:8000",
      );
      out({ reading });
      break;
    }
    case "vision_configure": {
      // The dashboard telling vision its station; the answer is canned, the request kept.
      const result = await configureLocalVision(
        data.station,
        canned({ "/config": data.response }, data.status ?? 200) as never,
        "http://127.0.0.1:8000",
        data.refresh ?? false,
      );
      out({ result, sent });
      break;
    }
    default:
      throw new Error(`unknown kind ${kind}`);
  }
}

main().catch((error) => {
  console.error(String(error?.message ?? error));
  process.exit(1);
});
