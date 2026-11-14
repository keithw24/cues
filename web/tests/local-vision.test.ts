import assert from "node:assert/strict";
import test from "node:test";
import {
  configureLocalVision,
  startLocalVisionSync,
  LOCAL_VISION_URL,
} from "../lib/local-vision.ts";
import { isEnabled } from "../lib/flags.ts";

type Call = { url: string; init: RequestInit };

function fakeFetch(respond: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetcher = async (url: string, init: RequestInit) => {
    const call = { url, init };
    calls.push(call);
    return respond(call);
  };
  return { calls, fetcher };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function fakeAuth() {
  let listener: ((event: string, session: unknown) => void) | null = null;
  let unsubscribed = false;
  return {
    client: {
      auth: {
        onAuthStateChange(cb: (event: string, session: unknown) => void) {
          listener = cb;
          return {
            data: { subscription: { unsubscribe: () => (unsubscribed = true) } },
          };
        },
      },
    } as never,
    signIn: () => listener?.("SIGNED_IN", { user: { id: "teacher-1" } }),
    signOut: () => listener?.("SIGNED_OUT", null),
    get unsubscribed() {
      return unsubscribed;
    },
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("vision station handoff defaults on and its =0 override turns it off", () => {
  assert.equal(isEnabled("web.vision_station_config", {}), true);
  assert.equal(
    isEnabled("web.vision_station_config", {
      CUES_FLAG_WEB_VISION_STATION_CONFIG: "0",
    }),
    false,
  );
});

test("sends the resolved station to vision on loopback only, with no credentials", async () => {
  const { calls, fetcher } = fakeFetch(() =>
    json(200, { station_id: "S2", changed: true }),
  );
  assert.equal(await configureLocalVision("S2", fetcher), "configured");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:8000/config");
  assert.equal(new URL(LOCAL_VISION_URL).hostname, "127.0.0.1");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "omit");
  assert.deepEqual(calls[0].init.headers, { "Content-Type": "application/json" });
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { station_id: "S2" });
});

test("same station is reported unchanged", async () => {
  const { fetcher } = fakeFetch(() => json(200, { station_id: "S1", changed: false }));
  assert.equal(await configureLocalVision("S1", fetcher), "unchanged");
});

test("invalid station ids are never sent", async () => {
  const { calls, fetcher } = fakeFetch(() => json(200, {}));
  for (const bad of ["", "S 1", "S1;x", "../S1", "S".repeat(65)])
    assert.equal(await configureLocalVision(bad, fetcher), "invalid");
  assert.equal(calls.length, 0);
});

test("pinned and unreachable vision are reported, not thrown", async () => {
  assert.equal(
    await configureLocalVision("S2", fakeFetch(() => json(409, {})).fetcher),
    "pinned",
  );
  assert.equal(
    await configureLocalVision("S2", fakeFetch(() => json(422, {})).fetcher),
    "unavailable",
  );
  assert.equal(
    await configureLocalVision(
      "S2",
      fakeFetch(() => Promise.reject(new TypeError("Failed to fetch"))).fetcher,
    ),
    "unavailable",
  );
});

test("sync sends only while a teacher is signed in, and re-sends for vision restarts", async () => {
  const auth = fakeAuth();
  const { calls, fetcher } = fakeFetch(() => json(200, { changed: false }));
  const results: string[] = [];
  const stop = startLocalVisionSync(auth.client, "S1", {
    fetcher,
    intervalMs: 5,
    onResult: (r) => results.push(r),
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(calls.length, 0, "nothing is sent before sign-in");
  auth.signIn();
  await tick();
  assert.ok(calls.length >= 1);
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.ok(calls.length >= 2, "the station is re-sent periodically");
  assert.ok(calls.every((c) => JSON.parse(String(c.init.body)).station_id === "S1"));
  auth.signOut();
  await tick();
  const afterSignOut = calls.length;
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(calls.length, afterSignOut, "signed out: nothing is sent");
  stop();
  assert.equal(auth.unsubscribed, true);
  assert.ok(results.every((r) => r === "unchanged"));
});

test("two teachers' browsers configure their own laptops' stations", async () => {
  const keith = fakeFetch(() => json(200, { changed: true }));
  const michelle = fakeFetch(() => json(200, { changed: true }));
  await configureLocalVision("S1", keith.fetcher);
  await configureLocalVision("S2", michelle.fetcher);
  assert.deepEqual(JSON.parse(String(keith.calls[0].init.body)), { station_id: "S1" });
  assert.deepEqual(JSON.parse(String(michelle.calls[0].init.body)), { station_id: "S2" });
});
