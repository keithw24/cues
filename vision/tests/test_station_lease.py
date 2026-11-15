"""One camera per station: a second camera is refused and pauses; it takes over later."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vision.app import create_app
from vision.camera import FakeCamera
from vision.pipeline import Pipeline
from vision.session_sync import StationSessionState, StationSessionSync
from vision.station import ActiveStation
from vision.station_lease import LeaseStatus, StationLease
from vision.tests.test_session_sync import Client, session


class Database(Client):
    """The session fake plus a writer lease the test controls."""

    def __init__(self, rows):
        super().__init__(rows)
        self.granted = True
        self.error = None
        self.leases = []

    def rpc(self, name, args):
        if name in ("claim_station_writer", "release_station_writer"):
            self.leases.append((name, args))
            if self.error is not None:
                raise self.error
            data = {"granted": self.granted, "held_seconds_ago": 2.0}
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))
        return super().rpc(name, args)


def build(station="S1", **kw):
    now = datetime.now(UTC)
    active = session(station_id=station, started_at=now, ended_at=None)
    db = Database([active.model_dump(mode="json")])
    status = LeaseStatus()
    state = StationSessionState()
    holder = ActiveStation(station)
    lease = StationLease(db, status=status)
    sync = StationSessionSync(db, station=holder, state=state, lease=lease, **kw)
    return sync, db, state, status, holder, lease


def reported(db):
    return [name for name, _ in db.calls if name == "report_station_session"]


def test_the_camera_that_holds_the_station_works_normally():
    sync, db, state, status, _, lease = build()
    assert sync.check_once() is not None
    assert reported(db) == ["report_station_session"]
    assert state._lease is not None  # the session is pinned: frames are evaluated
    assert not status.refused
    claim = db.leases[0]
    assert claim[0] == "claim_station_writer"
    assert claim[1]["p_station_id"] == "S1" and claim[1]["p_writer_id"] == str(lease.writer_id)


def test_a_second_camera_is_refused_and_pauses_completely():
    sync, db, state, status, _, _ = build()
    db.granted = False  # another camera holds S1
    assert sync.check_once() is None
    assert reported(db) == []  # it never reports the station as ready
    assert state._lease is None  # no session is pinned: no frames are evaluated or written
    assert status.refused and status.snapshot()["held_seconds_ago"] == 2.0


def test_a_refused_camera_keeps_trying_and_takes_over_when_the_other_stops():
    sync, db, state, status, _, _ = build()
    db.granted = False
    for _ in range(3):  # refused on every poll
        assert sync.check_once() is None
    assert status.refused and reported(db) == []
    db.granted = True  # the other camera released the station
    assert sync.check_once() is not None
    assert not status.refused and reported(db) == ["report_station_session"]


def test_a_network_failure_pauses_like_any_failed_sync():
    sync, db, state, status, _, _ = build()
    db.error = ConnectionError("private transport detail")
    with pytest.raises(ConnectionError):
        sync.check_once()
    assert state._lease is None and reported(db) == []


def test_without_the_database_function_the_camera_still_works_and_warns_once(caplog):
    sync, db, _, status, _, _ = build()

    class Missing(Exception):
        code = "PGRST202"

    db.error = Missing("Could not find the function public.claim_station_writer")
    assert sync.check_once() is not None  # not blocked: migration 1700 may not be applied yet
    assert sync.check_once() is not None
    assert caplog.text.count("apply migration 1700") == 1
    assert not status.refused


def test_changing_station_hands_the_old_one_over_and_claims_the_new_one():
    sync, db, _, _, holder, _ = build("S1")
    sync.check_once()
    holder.set("S2")
    db.rows = [session(station_id="S2", ended_at=None).model_dump(mode="json")]
    sync.check_once()
    names = [(n, a["p_station_id"]) for n, a in db.leases]
    assert ("release_station_writer", "S1") in names
    assert ("claim_station_writer", "S2") in names
    assert names.index(("release_station_writer", "S1")) < names.index(
        ("claim_station_writer", "S2")
    )


def test_stopping_hands_the_station_over_at_once():
    sync, db, _, status, _, lease = build()
    sync.check_once()
    sync.stop()
    release = [a for n, a in db.leases if n == "release_station_writer"]
    assert release == [{"p_station_id": "S1", "p_writer_id": str(lease.writer_id)}]
    assert not status.refused


def test_every_process_gets_its_own_writer_id():
    db = Database([])
    assert StationLease(db).writer_id != StationLease(db).writer_id


def test_a_failed_release_never_raises():
    sync, db, _, _, _, _ = build()
    sync.check_once()
    db.error = ConnectionError("offline")
    sync.stop()  # best effort: the lease expires on its own


def test_config_tells_the_dashboard_when_this_camera_is_being_refused():
    from vision.station_lease import STATUS

    app = create_app(Pipeline(FakeCamera(fps=30), []))
    local = {"client": ("127.0.0.1", 50123), "base_url": "http://127.0.0.1:8000"}
    try:
        with TestClient(app, **local) as client:
            assert client.get("/config").json()["station_busy"] is False
            STATUS.set(True, 3.0)
            assert client.get("/config").json()["station_busy"] is True
    finally:
        STATUS.set(False)
