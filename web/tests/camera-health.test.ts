import assert from "node:assert/strict";
import test from "node:test";
import {
  CAMERA_STOPPED,
  NO_STATION,
  NO_UPDATES,
  OTHER_CAMERA,
  OTHER_STATION,
  SERVICE_DOWN,
  cameraHealth,
  readLocalVision,
  updatesFresh,
  type LocalVisionReading,
} from "../lib/camera-health.ts";

const ok = (over: Partial<Extract<LocalVisionReading, { reachable: true }>> = {}) =>
  ({
    reachable: true,
    cameraOpen: true,
    frameAgeSeconds: 0.2,
    stationId: "S1",
    pinned: false,
    stationBusy: false,
    ...over,
  }) as LocalVisionReading;
const base = { station: "S1", updatesFresh: true, inView: 1, conflict: false };
const value = (h: ReturnType<typeof cameraHealth>, key: string) =>
  h.items.find((item) => item.key === key)?.value;

test("before the first reading nothing is claimed", () => {
  const h = cameraHealth({ ...base, vision: null });
  assert.equal(h.problem, null);
  assert.ok(h.items.every((item) => item.value === "Checking"));
});

test("everything working shows four good words and no problem", () => {
  const h = cameraHealth({ ...base, vision: ok() });
  assert.equal(h.problem, null);
  assert.deepEqual(h.items.map((item) => item.value), ["On", "Set", "Arriving", "None"]);
});

test("each cause gets its own message", () => {
  assert.equal(cameraHealth({ ...base, vision: { reachable: false } }).problem, SERVICE_DOWN);
  assert.equal(cameraHealth({ ...base, vision: ok({ stationId: null }) }).problem, NO_STATION);
  assert.equal(cameraHealth({ ...base, vision: ok({ stationId: "S2" }) }).problem, OTHER_STATION);
  assert.equal(
    cameraHealth({ ...base, vision: ok({ cameraOpen: false, frameAgeSeconds: null }) }).problem,
    CAMERA_STOPPED,
  );
  assert.equal(
    cameraHealth({ ...base, vision: ok({ frameAgeSeconds: 9 }) }).problem,
    CAMERA_STOPPED,
  );
  assert.equal(
    cameraHealth({ ...base, updatesFresh: false, inView: 0, vision: ok() }).problem,
    NO_UPDATES,
  );
});

test("another camera refused is reported from either side and comes first", () => {
  const here = cameraHealth({ ...base, vision: ok({ stationBusy: true }) });
  assert.equal(here.problem, OTHER_CAMERA);
  assert.equal(value(here, "other-camera"), "One refused");
  const elsewhere = cameraHealth({ ...base, conflict: true, vision: ok() });
  assert.equal(elsewhere.problem, OTHER_CAMERA);
  // Even when this laptop's service is down, the database still says a camera was refused.
  assert.equal(cameraHealth({ ...base, conflict: true, vision: { reachable: false } }).problem, OTHER_CAMERA);
});

test("an empty room is not a fault: updates arrive, no one is in view", () => {
  const h = cameraHealth({ ...base, inView: 0, vision: ok() });
  assert.equal(h.problem, null);
  assert.equal(value(h, "updates"), "Arriving, no one in view");
});

test("updatesFresh needs a recent, valid time", () => {
  const now = Date.parse("2026-11-14T12:00:10Z");
  assert.equal(updatesFresh(["2026-11-14T12:00:08Z"], now), true);
  assert.equal(updatesFresh(["2026-11-14T12:00:01Z"], now), false);
  assert.equal(updatesFresh([null, undefined, "nonsense"], now), false);
  assert.equal(updatesFresh([], now), false);
});

test("readLocalVision reads camera, station and busy flags from loopback only", async () => {
  const seen: string[] = [];
  const fetcher = async (url: string) => {
    seen.push(url);
    return new Response(
      JSON.stringify(
        url.endsWith("/health")
          ? { camera_open: true, frame_age_seconds: 0.4 }
          : { station_id: "S1", pinned: true, station_busy: false },
      ),
    );
  };
  const reading = await readLocalVision(fetcher as never);
  assert.deepEqual(reading, {
    reachable: true,
    cameraOpen: true,
    frameAgeSeconds: 0.4,
    stationId: "S1",
    pinned: true,
    stationBusy: false,
  });
  assert.ok(seen.every((url) => url.startsWith("http://127.0.0.1:8000/")));
});

test("a failing or refusing service reads as not running here", async () => {
  const down = async () => {
    throw new Error("refused");
  };
  assert.deepEqual(await readLocalVision(down as never), { reachable: false });
  const bad = async () => new Response("no", { status: 500 });
  assert.deepEqual(await readLocalVision(bad as never), { reachable: false });
});
