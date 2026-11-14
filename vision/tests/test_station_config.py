"""Station handoff: the dashboard sets this laptop's station; stations never mix."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shared.contracts import Session
from vision import station as station_module
from vision.activities import CurrentTasks
from vision.app import create_app
from vision.camera import FakeCamera, Frame
from vision.people import PersonTracker
from vision.perception import Match
from vision.pipeline import Pipeline
from vision.session_sync import StationSessionState, StationSessionSync
from vision.stages.s00_session import SessionStage
from vision.stages.s05_people import PeopleStage
from vision.stages.s50_status import StatusStage
from vision.station import ActiveStation, InvalidStationError, StationPinnedError
from vision.tests.test_people import pose
from vision.tests.test_status import RecordingEmitter

LOCAL = {"client": ("127.0.0.1", 50123), "base_url": "http://127.0.0.1:8000"}


# ---- fakes ------------------------------------------------------------------
class Db:
    """A tiny shared Supabase stand-in that honours the filters vision uses."""

    def __init__(self):
        self.sessions: list[dict] = []
        self.reports: list[dict] = []
        self.seat_state: dict[str, dict] = {}  # upsert on seat_id, as in Supabase
        self.lock = threading.Lock()

    def add_session(self, station_id: str, activity: str = "thumbs_up") -> dict:
        row = dict(
            id=str(uuid4()),
            station_id=station_id,
            current_activity_id=activity,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            revision=0,
        )
        self.sessions.append(row)
        return row

    def table(self, _name):
        return Query(self)

    def rpc(self, name, args):
        with self.lock:
            self.reports.append(args)
        return SimpleNamespace(execute=lambda: None)


class Query:
    def __init__(self, db):
        self.db = db
        self.filters = []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def is_(self, column, _null):
        self.filters.append(lambda r: r.get(column) is None)
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        with self.db.lock:
            rows = [dict(r) for r in self.db.sessions if all(f(r) for f in self.filters)]
        return SimpleNamespace(data=rows)


class TableEmitter(RecordingEmitter):
    """Records rows like RecordingEmitter and upserts seat_state into the shared Db."""

    def __init__(self, db):
        super().__init__()
        self.db = db

    def update_seat_state(self, state):
        super().update_seat_state(state)
        row = self.states[-1]
        with self.db.lock:
            self.db.seat_state[row["seat_id"]] = row


class StationZones:
    """One person per laptop, named from the frame's station, like PersonTracker ids."""

    mode = "people"

    def ids(self, ctx):
        return [f"{ctx['station_id']}-P1"] if ctx.get("station_id") else []


class Laptop:
    """One teacher's laptop: its own vision process state, sharing only the Db."""

    def __init__(self, db, station_id=None, tasks=None):
        self.t = 100.0  # a fake monotonic clock, advanced 0.1 s per frame
        self.station = ActiveStation(station_id)
        self.lease = StationSessionState(lambda: self.t)
        self.tasks = tasks or CurrentTasks("thumbs_up")
        self.station.subscribe(lambda *_: (self.lease.invalidate(), self.tasks.reset()))
        self.people = PeopleStage(detector=object(), station=self.station)
        self.pin = SessionStage(self.lease, station=self.station)
        self.emitter = TableEmitter(db)
        self.status = StatusStage(
            emitter=self.emitter, tasks=self.tasks, zones=StationZones(), station=self.station
        )
        self.sync = StationSessionSync(db, self.station, self.lease, poll_seconds=0.01)
        self.image = np.zeros((48, 64, 3), np.uint8)

    def frame(self, score=0.9, poll=True):
        self.t += 0.1
        if poll:
            self.sync.check_once()  # keeps the lease fresh, as the 1 s poll does
        frame = Frame(self.image, self.t, 0)
        ctx = {}
        self.pin.process(frame, ctx)
        self.people._follow_station(ctx)
        seat = f"{ctx['station_id']}-P1" if ctx["station_id"] else None
        if seat:
            session = ctx.get("session")
            activity = session.current_activity_id if session else "thumbs_up"
            ctx.update(
                people={seat: object()},
                hands={seat: []},
                faces={seat: object()},
                match={seat: Match(activity, score)},
            )
        self.status.process(frame, ctx)
        return ctx


# ---- the station holder -------------------------------------------------------
@pytest.mark.parametrize("bad", ["", " S1", "S1 ", "S1;drop", "../S1", "S" * 65, None, 1, ["S1"]])
def test_invalid_station_ids_are_rejected(bad):
    with pytest.raises(InvalidStationError):
        ActiveStation().set(bad)


def test_same_station_is_idempotent_and_does_not_reset():
    current = ActiveStation()
    changes = []
    current.subscribe(lambda old, new: changes.append((old, new)))
    assert current.set("S1") is True
    gen = current.generation
    assert current.set("S1") is False
    assert current.generation == gen and changes == [(None, "S1")]


def test_normal_start_has_no_station_and_needs_no_env():
    current = station_module.from_env({})
    assert current.get() is None and current.pinned is False


def test_dev_override_pins_the_station():
    current = station_module.from_env({"CUES_STATION_ID": "S7"})
    assert current.get() == "S7" and current.pinned
    assert current.set("S7") is False  # the dashboard may confirm the same station
    with pytest.raises(StationPinnedError):
        current.set("S2")
    assert current.get() == "S7"


def test_flag_off_keeps_the_old_s1_default():
    current = station_module.from_env({"CUES_FLAG_VISION_STATION_CONFIG": "0"})
    assert current.get() == "S1"


# ---- POST /config -------------------------------------------------------------
@pytest.fixture
def unconfigured(monkeypatch):
    current = ActiveStation()
    monkeypatch.setattr(station_module, "STATION", current)
    return current


@pytest.fixture
def api(unconfigured):
    with TestClient(create_app(Pipeline(FakeCamera(fps=30), [])), **LOCAL) as client:
        yield client


def test_vision_starts_without_a_station_and_reports_it(api):
    assert api.get("/health").json()["station_id"] is None
    assert api.get("/config").json() == {"station_id": None, "pinned": False}


def test_local_dashboard_sets_the_station(api, unconfigured):
    headers = {"Origin": "http://localhost:3000"}
    r = api.post("/config", json={"station_id": "S2"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"station_id": "S2", "pinned": False, "changed": True}
    assert unconfigured.get() == "S2"
    again = api.post("/config", json={"station_id": "S2"}, headers=headers)
    assert again.json()["changed"] is False
    assert api.get("/health").json()["station_id"] == "S2"


@pytest.mark.parametrize(
    "body", [{"station_id": "S 1"}, {"station_id": ""}, {"station_id": 5}, {"station": "S1"}, {}]
)
def test_invalid_config_is_rejected(api, unconfigured, body):
    assert api.post("/config", json=body).status_code == 422
    assert unconfigured.get() is None


def test_config_needs_json_so_cross_site_forms_cannot_send_it(api, unconfigured):
    r = api.post("/config", content='{"station_id": "S1"}', headers={"Content-Type": "text/plain"})
    assert r.status_code in (415, 422)
    assert unconfigured.get() is None


def test_other_websites_cannot_configure_vision(api, unconfigured):
    r = api.post("/config", json={"station_id": "S1"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and unconfigured.get() is None


def test_rebound_host_names_are_refused(api, unconfigured):
    r = api.post("/config", json={"station_id": "S1"}, headers={"Host": "evil.example:8000"})
    assert r.status_code == 403 and unconfigured.get() is None


def test_remote_peers_are_refused(unconfigured):
    app = create_app(Pipeline(FakeCamera(fps=30), []))
    remote = {"client": ("192.168.1.20", 5555), "base_url": "http://127.0.0.1:8000"}
    with TestClient(app, **remote) as client:
        assert client.post("/config", json={"station_id": "S1"}).status_code == 403
        assert client.get("/config").status_code == 403
    assert unconfigured.get() is None


def test_pinned_station_refuses_a_different_one(monkeypatch):
    monkeypatch.setattr(station_module, "STATION", ActiveStation("S1", pinned=True))
    with TestClient(create_app(Pipeline(FakeCamera(fps=30), [])), **LOCAL) as client:
        assert client.post("/config", json={"station_id": "S1"}).json()["changed"] is False
        assert client.post("/config", json={"station_id": "S2"}).status_code == 409


def test_flag_off_serves_no_config_and_the_service_still_works(monkeypatch, unconfigured):
    monkeypatch.setenv("CUES_FLAG_VISION_STATION_CONFIG", "0")
    with TestClient(create_app(Pipeline(FakeCamera(fps=30), [])), **LOCAL) as client:
        assert client.post("/config", json={"station_id": "S1"}).status_code in (404, 405)
        assert client.get("/health").json()["camera_open"] is True
    assert unconfigured.get() is None


# ---- nothing is written before a station is set --------------------------------
def test_no_station_means_no_session_reads_and_no_writes():
    db = Db()
    db.add_session("S1")
    laptop = Laptop(db)
    assert laptop.sync.check_once() is None and db.reports == []
    for _ in range(5):
        ctx = laptop.frame()
    assert ctx["status"] == {}
    assert laptop.emitter.states == [] and laptop.emitter.events == [] and db.seat_state == {}


def test_tracks_before_a_station_use_a_local_prefix_only():
    stage = PeopleStage(detector=object(), station=ActiveStation())
    assert stage.tracker.update(0.0, [pose(0.3)]).keys() == {"local-P1"}


# ---- station switch -------------------------------------------------------------
def test_station_switch_resets_every_cache():
    db = Db()
    s1 = db.add_session("S1", "raise_hand")
    s2 = db.add_session("S2", "thumbs_up")
    laptop = Laptop(db, "S1")
    laptop.tasks.set_class_task("raise_hand")
    laptop.tasks.set_override("S1-P1", "raise_hand")
    laptop.people.tracker.update(0.0, [pose(0.3)])
    assert laptop.sync.check_once().id.hex == s1["id"].replace("-", "")
    for _ in range(30):
        ctx = laptop.frame()
    assert ctx["status"] == {"S1-P1": "done"}

    assert laptop.station.set("S2") is True
    # Session lease, tasks, tracking and status are all dropped.
    assert laptop.lease.for_frame(laptop.t + 1) is None
    assert laptop.tasks.class_task == "thumbs_up" and laptop.tasks.overrides == {}
    states_before = len(laptop.emitter.states)
    ctx = laptop.frame(poll=False)
    assert ctx["session"] is None and ctx["status"] == {}  # the S1 lease is never reused
    assert laptop.status._trackers == {} and laptop.status._last_state == {}
    assert laptop.people.tracker.tracks == {}
    assert laptop.people.tracker.update(0.0, [pose(0.3)]).keys() == {"S2-P1"}
    assert len(laptop.emitter.states) == states_before

    laptop.sync.check_once()
    ctx = laptop.frame(score=0.0)
    assert ctx["status"] == {"S2-P1": "in_progress"}  # S1's "done" did not carry over
    new_rows = laptop.emitter.states[states_before:]
    assert {r["seat_id"] for r in new_rows} == {"S2-P1"}
    assert {r["session_id"] for r in new_rows} == {s2["id"]}
    assert db.reports[-1]["p_station_id"] == "S2"


def test_a_poll_that_spans_a_switch_is_discarded():
    db = Db()
    db.add_session("S1")
    laptop = Laptop(db, "S1")
    original = db.table

    def switching_table(name):
        laptop.station.set("S2")  # the teacher changes station while S1 is being read
        db.table = original
        return original(name)

    db.table = switching_table
    assert laptop.sync.check_once() is None
    assert laptop.lease.for_frame(laptop.t + 1) is None


def test_session_of_another_station_is_never_used():
    lease = StationSessionState()
    lease.confirm(
        Session.model_validate(
            dict(
                id=uuid4(),
                station_id="S1",
                current_activity_id="thumbs_up",
                started_at=datetime.now(UTC),
                ended_at=None,
                revision=0,
            )
        )
    )
    ctx = {}
    SessionStage(lease, station=ActiveStation("S2")).process(Frame(None, 1e9, 0), ctx)
    assert ctx["session"] is None


def test_global_station_change_resets_shared_session_and_tasks(monkeypatch):
    from vision import activities, session_sync

    lease = StationSessionState()
    tasks = CurrentTasks("thumbs_up")
    monkeypatch.setattr(session_sync, "STATION_SESSION", lease)
    monkeypatch.setattr(activities, "TASKS", tasks)
    current = ActiveStation("S1")
    current.subscribe(station_module._reset_shared_state)
    lease.confirm(None)
    tasks.set_class_task("raise_hand")
    current.set("S2")
    assert lease._lease is None and tasks.class_task == "thumbs_up"


# ---- two teachers, two laptops -----------------------------------------------------
def test_two_laptops_keep_stations_sessions_and_seats_apart():
    db = Db()
    s1 = db.add_session("S1", "thumbs_up")
    s2 = db.add_session("S2", "thumbs_up")
    keith, michelle = Laptop(db), Laptop(db)
    keith.station.set("S1")  # each dashboard sends its teacher's station
    michelle.station.set("S2")
    for laptop in (keith, michelle):
        laptop.sync.check_once()
    for _ in range(30):
        k, m = keith.frame(), michelle.frame()
    assert k["status"] == {"S1-P1": "done"} and m["status"] == {"S2-P1": "done"}

    # Activity change on S1 does not touch S2.
    db.sessions[0]["current_activity_id"] = "raise_hand"
    db.sessions[0]["revision"] = 1
    for laptop in (keith, michelle):
        laptop.sync.check_once()
    k, m = keith.frame(score=0.0), michelle.frame(score=0.0)
    assert keith.lease.for_frame(keith.t).current_activity_id == "raise_hand"
    assert michelle.lease.for_frame(michelle.t).current_activity_id == "thumbs_up"
    assert m["status"] == {"S2-P1": "done"}  # S2's tracker was not reset by S1's change
    assert k["status"] == {"S1-P1": "in_progress"}

    # Activity change on S2 does not touch S1.
    db.sessions[1]["current_activity_id"] = "raise_hand"
    db.sessions[1]["revision"] = 1
    for laptop in (keith, michelle):
        laptop.sync.check_once()
    assert keith.lease.for_frame(keith.t + 0.1).revision == 1
    assert keith.lease.for_frame(keith.t + 0.1).id.hex == s1["id"].replace("-", "")
    assert michelle.lease.for_frame(michelle.t + 0.1).id.hex == s2["id"].replace("-", "")

    k_rows, m_rows = keith.emitter.states, michelle.emitter.states
    assert {r["seat_id"] for r in k_rows} == {"S1-P1"}
    assert {r["seat_id"] for r in m_rows} == {"S2-P1"}
    assert {r["session_id"] for r in k_rows} == {s1["id"]}
    assert {r["session_id"] for r in m_rows} == {s2["id"]}
    assert {e["station_id"] for e in keith.emitter.events} == {"S1"}
    assert {e["station_id"] for e in michelle.emitter.events} == {"S2"}
    assert set(db.seat_state) == {"S1-P1", "S2-P1"}  # no shared seat rows
    assert {r["p_station_id"] for r in db.reports} == {"S1", "S2"}


def test_two_laptops_run_at_the_same_time():
    db = Db()
    db.add_session("S1")
    db.add_session("S2")
    laptops = [Laptop(db, "S1"), Laptop(db, "S2")]
    for laptop in laptops:
        laptop.sync.start()
    try:
        errors = []

        def run(laptop):
            try:
                for _ in range(200):
                    laptop.frame(poll=False)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(lp,)) for lp in laptops]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
    finally:
        for laptop in laptops:
            laptop.sync.stop()
    assert errors == []
    for laptop, station_id in zip(laptops, ("S1", "S2"), strict=True):
        assert {r["seat_id"] for r in laptop.emitter.states} <= {f"{station_id}-P1"}
    assert set(db.seat_state) <= {"S1-P1", "S2-P1"}


def test_legacy_activity_sync_ignores_another_stations_session():
    from vision.activity_sync import ActivitySync

    db = Db()
    row = db.add_session("S1", "raise_hand")
    tasks = CurrentTasks("thumbs_up")
    s2 = ActiveStation("S2")
    sync = ActivitySync(db, row["id"], tasks=tasks, station=s2)
    assert sync.check_once() is None and tasks.class_task == "thumbs_up"
    assert ActivitySync(db, row["id"], tasks=tasks, station=ActiveStation()).check_once() is None
    assert ActivitySync(db, row["id"], tasks=tasks, station=ActiveStation("S1")).check_once() == (
        "raise_hand"
    )


def test_people_stage_ids_follow_the_station():
    current = ActiveStation("S1")
    stage = PeopleStage(detector=object(), station=current, tracker=PersonTracker("S1"))
    ctx = {}
    stage._follow_station(ctx)
    assert ctx["station_id"] == "S1"
    current.set("S2")
    stage._follow_station(ctx)
    assert ctx["station_id"] == "S2" and stage.tracker.station_id == "S2"
