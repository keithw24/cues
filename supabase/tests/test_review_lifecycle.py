"""Review lifecycle (migration 1300). Real PostgreSQL, temporary local cluster.

    LC_ALL=en_US.UTF-8 uv run pytest supabase/tests/test_review_lifecycle.py

Never uses DATABASE_URL or hosted credentials. Skipped when initdb/pg_ctl/psql are missing.
Migrations up to 1200 are replayed and the data we actually found is seeded (duplicate
pending reviews, pending reviews in ended sessions); only then is 1300 applied, so the
one-time cleanup is tested as well as the triggers.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase/migrations"
LIFECYCLE = "20261114001300_review_lifecycle.sql"
TEACHER = "00000000-0000-4000-8000-0000000000c1"
S_ENDED = "00000000-0000-4000-8000-0000000000d1"  # S1, already ended
S_RUNNING = "00000000-0000-4000-8000-0000000000d2"  # S1, running
S_OTHER = "00000000-0000-4000-8000-0000000000d3"  # S2, running


def review(session, seat, activity, n, status="pending", age_minutes=0):
    """SQL for one review row; n keeps each evaluation distinct (it is unique).

    Reviews are always created pending (a database rule); other statuses are reached by
    resolving the row afterwards, as in real use.
    """
    insert = f"""
      insert into public.teacher_reviews(id, created_at, session_id, seat_id, activity_id,
        priority, evaluation, decision, rationale, evidence_used)
      values (gen_random_uuid(), now() - interval '{age_minutes} minutes', '{session}', '{seat}',
        '{activity}', 'normal',
        jsonb_build_object('session_id','{session}','seat_id','{seat}','activity_id','{activity}',
          'escalation', jsonb_build_object('priority','normal','should_evaluate', true),
          'progress', jsonb_build_object('trend','stalled'), 'n', {n}),
        'teacher_review_warranted', 'Stalled.', '["current_progress"]');"""
    if status == "pending":
        return insert
    return (
        insert
        + f"""
      update public.teacher_reviews set status='{status}', resolved_at=now()
        where session_id='{session}' and evaluation->>'n' = '{n}';"""
    )


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-review-lifecycle-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55499",
            "PGDATABASE": "postgres",
            "PGUSER": os.environ.get("USER", ""),
        }

        def run(*args):
            return subprocess.run(args, capture_output=True, text=True, check=True)

        run("initdb", "-D", data, "-A", "trust", "--no-locale")
        run(
            "pg_ctl",
            "-D",
            data,
            "-l",
            str(Path(directory) / "postgres.log"),
            "-o",
            f"-k {directory} -p 55499 -h ''",
            "-w",
            "start",
        )

        def sql(statement, check=True):
            result = subprocess.run(
                ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1"],
                input=statement,
                env=env,
                text=True,
                capture_output=True,
            )
            if check and result.returncode:
                raise AssertionError(result.stderr)
            return result

        try:
            sql("""
              create role anon; create role authenticated; create role service_role bypassrls;
              create schema auth;
              create table auth.users(id uuid primary key);
              create function auth.uid() returns uuid language sql as $$
                select (nullif(current_setting('request.jwt.claims',true),'')::jsonb
                  ->>'sub')::uuid $$;
              create function auth.role() returns text language sql as $$
                select nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role' $$;
              create publication supabase_realtime;
            """)
            files = sorted(MIGRATIONS.glob("*.sql"))
            assert LIFECYCLE in [f.name for f in files]
            for file in files:
                if file.name < LIFECYCLE:
                    sql(file.read_text())
            sql(f"""
              insert into auth.users values ('{TEACHER}');
              insert into public.stations(id, name) values ('S1','One'),('S2','Two');
              insert into public.station_teachers(station_id, teacher_id)
                values ('S1','{TEACHER}');
              insert into public.activities(id, name, check_type, no_progress_seconds, config)
                values ('raise_hand','Raise your hand','rule',30,'{{}}'),
                       ('thumbs_up','Thumbs up','gesture',30,'{{}}');
              insert into public.sessions(id, station_id, current_activity_id, teacher_id, ended_at)
                values ('{S_ENDED}','S1','raise_hand','{TEACHER}', now() - interval '2 hours');
              insert into public.sessions(id, station_id, current_activity_id, teacher_id)
                values ('{S_RUNNING}','S1','raise_hand','{TEACHER}'),
                       ('{S_OTHER}','S2','raise_hand','{TEACHER}');
            """)
            # What we found: many pending reviews for one person, in ended and running sessions.
            seeded = [
                review(S_ENDED, "S1-P1", "raise_hand", 1),
                review(S_ENDED, "S1-P1", "raise_hand", 2),
                review(S_ENDED, "S1-P2", "raise_hand", 3),
                review(S_ENDED, "S1-P1", "raise_hand", 4, status="confirmed"),
                review(S_RUNNING, "S1-P1", "raise_hand", 5, age_minutes=30),  # oldest: kept
                review(S_RUNNING, "S1-P1", "raise_hand", 6, age_minutes=20),
                review(S_RUNNING, "S1-P1", "raise_hand", 7, age_minutes=10),
                review(S_RUNNING, "S1-P2", "raise_hand", 8),
                review(S_OTHER, "S2-P1", "raise_hand", 9),
            ]
            sql("".join(seeded))
            sql((MIGRATIONS / LIFECYCLE).read_text())
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def scalar(db, query):
    return db(query).stdout.strip()


def pending(db, session, seat=None):
    where = f"session_id='{session}' and status='pending'"
    if seat:
        where += f" and seat_id='{seat}'"
    return int(scalar(db, f"select count(*) from public.teacher_reviews where {where};"))


# --- the one-time cleanup on the data we found --------------------------------------
def test_pending_reviews_of_ended_sessions_were_closed(db):
    assert pending(db, S_ENDED) == 0
    assert (
        scalar(
            db,
            f"select count(*) from public.teacher_reviews "
            f"where session_id='{S_ENDED}' and status='expired' and resolved_at >= created_at;",
        )
        == "3"
    )


def test_a_teachers_own_decisions_are_never_rewritten(db):
    assert (
        scalar(
            db,
            f"select status from public.teacher_reviews where session_id='{S_ENDED}' "
            "and evaluation->>'n' = '4';",
        )
        == "confirmed"
    )


def test_duplicates_in_a_running_session_collapse_to_the_oldest(db):
    assert pending(db, S_RUNNING, "S1-P1") == 1
    kept = scalar(
        db,
        f"select evaluation->>'n' from public.teacher_reviews "
        f"where session_id='{S_RUNNING}' and seat_id='S1-P1' and status='pending';",
    )
    assert kept == "5"  # the oldest stays open, the newer duplicates were closed
    assert pending(db, S_RUNNING, "S1-P2") == 1  # a different person is untouched
    assert pending(db, S_OTHER) == 1  # another station's session is untouched


# --- one open review per person, activity and session ----------------------------------
def test_a_second_open_review_for_the_same_person_is_refused(db):
    refused = db(review(S_RUNNING, "S1-P1", "raise_hand", 100), check=False)
    assert refused.returncode and "teacher_reviews_one_open_per_seat_activity" in refused.stderr
    assert pending(db, S_RUNNING, "S1-P1") == 1


def test_other_people_and_other_activities_may_each_have_one(db):
    db(review(S_RUNNING, "S1-P3", "raise_hand", 101))  # another person
    db(review(S_RUNNING, "S1-P1", "thumbs_up", 102))  # another activity
    assert pending(db, S_RUNNING, "S1-P3") == 1
    assert (
        scalar(
            db,
            f"select count(*) from public.teacher_reviews where session_id='{S_RUNNING}' "
            "and seat_id='S1-P1' and activity_id='thumbs_up' and status='pending';",
        )
        == "1"
    )


def test_a_new_review_may_open_after_the_old_one_is_resolved(db):
    db(
        f"update public.teacher_reviews set status='dismissed', resolved_at=now() "
        f"where session_id='{S_OTHER}' and seat_id='S2-P1' and status='pending';"
    )
    db(review(S_OTHER, "S2-P1", "raise_hand", 103))
    assert pending(db, S_OTHER, "S2-P1") == 1


# --- closing a session closes its open reviews -----------------------------------------
def test_ending_a_session_closes_its_open_reviews(db):
    open_before = pending(db, S_RUNNING)
    assert open_before >= 3
    db(f"update public.sessions set ended_at = now() where id='{S_RUNNING}';")
    assert pending(db, S_RUNNING) == 0
    assert (
        int(
            scalar(
                db,
                f"select count(*) from public.teacher_reviews where session_id='{S_RUNNING}' "
                "and status='expired' and resolved_at is not null "
                "and resolved_at >= created_at;",
            )
        )
        >= open_before
    )


def test_other_sessions_keep_their_open_reviews(db):
    assert pending(db, S_OTHER) == 1  # ending S1's session did not touch S2's


def test_other_session_updates_do_not_close_reviews(db):
    db(f"update public.sessions set revision = revision + 1 where id='{S_OTHER}';")
    assert pending(db, S_OTHER) == 1


def test_a_review_that_arrives_after_its_session_ended_is_closed_at_once(db):
    db(review(S_ENDED, "S1-P9", "raise_hand", 200))
    assert pending(db, S_ENDED) == 0
    assert (
        scalar(
            db,
            f"select status from public.teacher_reviews where session_id='{S_ENDED}' "
            "and seat_id='S1-P9';",
        )
        == "expired"
    )


def test_the_end_session_rpc_closes_reviews_too(db):
    session = "00000000-0000-4000-8000-0000000000d4"
    db(f"""
      insert into public.stations(id, name) values ('S3','Three');
      insert into public.station_teachers(station_id, teacher_id) values ('S3','{TEACHER}');
      insert into public.sessions(id, station_id, current_activity_id, teacher_id)
        values ('{session}','S3','raise_hand','{TEACHER}');
    """)
    db(review(session, "S3-P1", "raise_hand", 300))
    assert pending(db, session) == 1
    ended = db(
        f"set role authenticated; select set_config('request.jwt.claims',"
        f'\'{{"sub":"{TEACHER}","role":"authenticated"}}\',false); '
        f"select public.end_station_session('S3','{session}',0);",
        check=False,
    )
    assert ended.returncode == 0, ended.stderr
    assert pending(db, session) == 0


# --- expired is for the system only ---------------------------------------------------
def test_an_expired_review_cannot_be_reopened_or_changed(db):
    for statement in (
        "update public.teacher_reviews set status='pending', resolved_at=null "
        f"where session_id='{S_ENDED}' and status='expired';",
        "update public.teacher_reviews set status='confirmed' "
        f"where session_id='{S_ENDED}' and status='expired';",
    ):
        refused = db(statement, check=False)
        assert refused.returncode and "review already resolved" in refused.stderr


def test_a_teacher_cannot_set_expired_through_the_review_action(db):
    review_id = scalar(
        db,
        f"select id from public.teacher_reviews where session_id='{S_OTHER}' "
        "and status='pending' limit 1;",
    )
    result = db(
        f"set role authenticated; select set_config('request.jwt.claims',"
        f'\'{{"sub":"{TEACHER}","role":"authenticated"}}\',false); '
        f"select * from public.resolve_teacher_review('{review_id}','expired');",
        check=False,
    )
    assert result.returncode and "invalid review action" in result.stderr


def test_browsers_cannot_run_the_expiry_functions(db):
    for function in ("expire_reviews_when_session_ends", "expire_review_of_ended_session"):
        denied = db(
            f"set role authenticated; select public.{function}();",
            check=False,
        )
        assert denied.returncode
