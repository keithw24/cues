"""'Mark as reviewed': a flagged child goes back to working and the timers restart."""

import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from vision.activities import CurrentTasks
from vision.people import PeopleGrouping
from vision.review_marks import ReviewMarks, ReviewMarkSync
from vision.stages.s50_status import StatusStage
from vision.status import SeatTracker
from vision.tests.test_seat_state import SESSION, RecordingEmitter, ctx_for, person_states, run
from vision.tests.test_status import GESTURE, ticks
from vision.tests.test_status import run as run_tracker

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


# ---- the tracker -----------------------------------------------------------------
def test_a_needs_help_child_goes_back_to_working_and_the_no_progress_timer_restarts():
    tr = SeatTracker("S1-P1", GESTURE)  # no_progress_seconds = 30
    assert "no_progress" in run_tracker(tr, ticks(0, 31, 0.1))
    assert tr.status == "needs_help"
    assert tr.acknowledge(T0) is True
    assert tr.status == "in_progress"
    # 24 s later: not flagged again yet (the timer restarted at the mark)...
    assert "no_progress" not in run_tracker(tr, ticks(31.1, 55, 0.1))
    assert tr.status == "in_progress"
    # ...and a fresh stall of 30 s flags them again.
    assert "no_progress" in run_tracker(tr, ticks(55.1, 63, 0.1))
    assert tr.status == "needs_help"


def test_a_review_status_child_can_be_flagged_for_review_again_after_a_mark():
    tr = SeatTracker("S1-P1", GESTURE)
    assert run_tracker(tr, ticks(0, 3, 0.65)) == ["review_needed"]
    assert tr.status == "review"
    tr.acknowledge(T0)
    assert tr.status == "in_progress"
    assert run_tracker(tr, ticks(3.1, 6.5, 0.65)) == ["review_needed"]  # a fresh 2 s in the band


def test_a_completed_task_stays_completed():
    tr = SeatTracker("S1-P1", GESTURE)
    assert run_tracker(tr, ticks(0, 1.2, 0.9)) == ["attempt_success"]
    assert tr.status == "done"
    assert tr.acknowledge(T0) is False
    assert tr.status == "done"


def test_a_mark_while_tracking_is_lost_returns_them_to_working_not_needs_help():
    tr = SeatTracker("S1-P1", GESTURE)
    run_tracker(tr, ticks(0, 31, 0.1))
    assert tr.status == "needs_help"
    run_tracker(tr, ticks(31.1, 36, None, hand=False, face=False))
    assert tr.status == "tracking_lost"
    tr.acknowledge(T0)
    assert tr.status == "tracking_lost"  # still out of view
    run_tracker(tr, ticks(36.1, 37, 0.1))
    assert tr.status == "in_progress"  # back in view, working


# ---- the status stage --------------------------------------------------------------
def flagged_stage():
    em = RecordingEmitter()
    marks = ReviewMarks()
    stage = StatusStage(
        emitter=em, tasks=CurrentTasks("raise_hand"), zones=PeopleGrouping(), marks=marks
    )
    steps = [(i * 0.5, ctx_for(score=0.0)) for i in range(70)]  # 35 s with no progress
    run(stage, steps)
    assert person_states(em)[-1]["status"] == "needs_help"
    return stage, em, marks


def frames(stage, start, seconds):
    for i in range(int(seconds * 2)):
        stage.process(SimpleNamespace(timestamp=start + i * 0.5, image=None), ctx_for(score=0.0))


def test_the_stage_puts_a_marked_child_back_to_working_and_restarts_the_timer():
    stage, em, marks = flagged_stage()
    marks.replace(str(SESSION), {"S1-P1": T0})
    frames(stage, 35.0, 0.5)
    assert person_states(em)[-1]["status"] == "in_progress"  # published at once
    frames(stage, 35.5, 24)  # well short of a fresh 30 s
    assert person_states(em)[-1]["status"] == "in_progress"
    frames(stage, 60.0, 8)
    assert person_states(em)[-1]["status"] == "needs_help"  # flagged again after a fresh stall


def test_the_same_or_an_older_mark_does_nothing_again():
    stage, em, marks = flagged_stage()
    marks.replace(str(SESSION), {"S1-P1": T0})
    frames(stage, 35.0, 1)  # acted on once
    frames(stage, 36.0, 31)  # flagged again by a fresh stall
    assert person_states(em)[-1]["status"] == "needs_help"
    marks.replace(str(SESSION), {"S1-P1": T0})  # the same mark, seen again on the next poll
    frames(stage, 67.0, 1)
    assert person_states(em)[-1]["status"] == "needs_help"
    marks.replace(str(SESSION), {"S1-P1": T0 - timedelta(minutes=5)})
    frames(stage, 68.0, 1)
    assert person_states(em)[-1]["status"] == "needs_help"
    marks.replace(str(SESSION), {"S1-P1": T0 + timedelta(minutes=1)})  # marked again: acts
    frames(stage, 69.0, 1)
    assert person_states(em)[-1]["status"] == "in_progress"


def test_a_mark_for_another_session_or_another_child_is_ignored():
    stage, em, marks = flagged_stage()
    marks.replace("00000000-0000-4000-8000-0000000000aa", {"S1-P1": T0})  # another session
    frames(stage, 35.0, 1)
    marks.replace(str(SESSION), {"S1-P2": T0})  # another child
    frames(stage, 36.0, 1)
    assert person_states(em)[-1]["status"] == "needs_help"


def test_a_mark_from_before_a_tracker_existed_does_not_reset_it():
    em = RecordingEmitter()
    marks = ReviewMarks()
    marks.replace(str(SESSION), {"S1-P1": T0})  # an old mark, already in the database
    stage = StatusStage(
        emitter=em, tasks=CurrentTasks("raise_hand"), zones=PeopleGrouping(), marks=marks
    )
    run(stage, [(i * 0.5, ctx_for(score=0.0)) for i in range(70)])
    assert person_states(em)[-1]["status"] == "needs_help"  # not reset by the old mark


# ---- the poller ----------------------------------------------------------------------
class Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def is_(self, *_):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        data = self.tables[name]
        if isinstance(data, Exception):
            raise data
        return Query(data)


class Station:
    def __init__(self, *values):
        self.values = list(values)

    def get(self):
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def sync_with(tables, station, marks=None):
    marks = marks or ReviewMarks()
    return ReviewMarkSync(Client(tables), station=station, marks=marks), marks


def test_the_poller_reads_the_current_sessions_marks():
    sync, marks = sync_with(
        {
            "sessions": [{"id": str(SESSION)}],
            "seat_review_marks": [{"seat_id": "S1-P1", "marked_at": "2026-11-14T12:00:00+00:00"}],
        },
        Station("S1"),
    )
    sync.check_once()
    assert marks.get(SESSION, "S1-P1") == T0
    assert marks.get(SESSION, "S1-P2") is None


def test_no_station_or_no_single_active_session_means_no_marks():
    marks = ReviewMarks()
    marks.replace(str(SESSION), {"S1-P1": T0})
    sync, _ = sync_with({"sessions": [], "seat_review_marks": []}, Station(None), marks)
    sync.check_once()  # vision has no teacher station yet
    assert marks.get(SESSION, "S1-P1") is None
    marks.replace(str(SESSION), {"S1-P1": T0})
    two = {"sessions": [{"id": "a"}, {"id": "b"}], "seat_review_marks": []}
    sync, _ = sync_with(two, Station("S1"), marks)
    sync.check_once()  # ambiguous: never guess a session
    assert marks.get(SESSION, "S1-P1") is None


def test_an_answer_read_for_the_old_station_is_dropped_when_the_station_changes():
    sync, marks = sync_with(
        {
            "sessions": [{"id": str(SESSION)}],
            "seat_review_marks": [{"seat_id": "S1-P1", "marked_at": "2026-11-14T12:00:00Z"}],
        },
        Station("S1", "S2"),  # the station changed while the read was in flight
    )
    sync.check_once()
    assert marks.get(SESSION, "S1-P1") is None


def test_the_poller_survives_a_missing_table_and_keeps_trying():
    sync, marks = sync_with(
        {"sessions": [{"id": str(SESSION)}], "seat_review_marks": RuntimeError("no such table")},
        Station("S1"),
    )
    sync.poll_seconds = 0.01
    sync.start()
    time.sleep(0.1)
    alive = sync._thread.is_alive()
    sync.stop()
    assert alive and sync._failing and threading.active_count() >= 1
