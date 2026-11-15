"""read_station_flags (migration 1600). Real PostgreSQL, temporary local cluster.

    LC_ALL=en_US.UTF-8 uv run pytest supabase/tests/test_station_flags.py

Never uses DATABASE_URL or hosted credentials. Skipped without initdb/pg_ctl/psql.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase/migrations"
TEACHER = "00000000-0000-4000-8000-0000000000a1"
OTHER_TEACHER = "00000000-0000-4000-8000-0000000000a2"
S_MINE = "00000000-0000-4000-8000-0000000000b1"  # S1, mine, running
S_SHARED = "00000000-0000-4000-8000-0000000000b2"  # S1, another teacher's session
S_ELSEWHERE = "00000000-0000-4000-8000-0000000000b3"  # S2


def event(session, station, seat, kind, minutes_ago):
    return f"""insert into public.events(session_id, station_id, seat_id, type, activity_id,
      payload, created_at) values ('{session}','{station}','{seat}','{kind}','raise_hand',
      '{{"secret":"never returned"}}', now() - interval '{minutes_ago} minutes');"""


def review(session, seat, n, minutes_ago, status="pending"):
    insert = f"""
      insert into public.teacher_reviews(id, created_at, session_id, seat_id, activity_id,
        priority, evaluation, decision, rationale, evidence_used)
      values (gen_random_uuid(), now() - interval '{minutes_ago} minutes', '{session}', '{seat}',
        'raise_hand', 'normal',
        jsonb_build_object('session_id','{session}','seat_id','{seat}','activity_id','raise_hand',
          'escalation', jsonb_build_object('priority','normal','should_evaluate', true),
          'progress', jsonb_build_object('trend','stalled'), 'n', {n}),
        'teacher_review_warranted', 'Stalled.', '["current_progress"]');"""
    if status == "pending":
        return insert
    return (
        insert
        + f"""update public.teacher_reviews set status='{status}', resolved_at=now()
      where session_id='{session}' and evaluation->>'n'='{n}';"""
    )


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-station-flags-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55501",
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
            f"-k {directory} -p 55501 -h ''",
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
            for file in sorted(MIGRATIONS.glob("*.sql")):
                sql(file.read_text())
            sql(f"""
              insert into auth.users values ('{TEACHER}'),('{OTHER_TEACHER}');
              insert into public.stations(id, name) values ('S1','One'),('S2','Two');
              insert into public.station_teachers(station_id, teacher_id)
                values ('S1','{TEACHER}'),('S1','{OTHER_TEACHER}'),('S2','{OTHER_TEACHER}');
              insert into public.activities(id, name, check_type, no_progress_seconds, config)
                values ('raise_hand','Raise your hand','rule',30,'{{}}') on conflict do nothing;
              insert into public.sessions(id, station_id, current_activity_id, teacher_id, ended_at)
                values ('{S_MINE}','S1','raise_hand','{TEACHER}', null),
                       ('{S_SHARED}','S1','raise_hand','{OTHER_TEACHER}',
                        now() - interval '3 hours'),
                       ('{S_ELSEWHERE}','S2','raise_hand','{OTHER_TEACHER}', null);
            """)
            sql(
                event(S_MINE, "S1", "S1-P1", "no_progress", 5)
                + event(S_MINE, "S1", "S1-P1", "review_needed", 20)
                + event(S_MINE, "S1", "S1-P2", "attempt_success", 8)  # not a flag
                + event(S_MINE, "S1", "S1-P1", "no_progress", 90)  # outside the hour
                + event(S_SHARED, "S1", "S1-P1", "no_progress", 10)  # another teacher's session
                + event(S_ELSEWHERE, "S2", "S2-P1", "no_progress", 10)  # another station
                + review(S_MINE, "S1-P1", 1, 30, status="confirmed")  # closed, must still show
                + review(S_MINE, "S1-P2", 2, 12)  # open
                + review(S_SHARED, "S1-P1", 3, 15)  # another teacher's
            )
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def flags(db, user, station="S1", since="null"):
    claims = f'{{"sub":"{user}","role":"authenticated"}}' if user else "{}"
    return db(
        f"set role authenticated; select set_config('request.jwt.claims','{claims}',false); "
        f"select seat_id || '/' || kind from public.read_station_flags('{station}', {since});",
        check=False,
    )


def kinds(result):
    return sorted(line for line in result.stdout.splitlines() if "/" in line)


def test_the_last_hour_has_vision_flags_and_reviews_of_every_status(db):
    got = flags(db, TEACHER)
    assert got.returncode == 0, got.stderr
    assert kinds(got) == sorted(
        ["S1-P1/no_progress", "S1-P1/review_needed", "S1-P1/review", "S1-P2/review"]
    )  # the confirmed review is still here; so is the open one


def test_only_flag_types_are_returned_not_other_events(db):
    assert not any("attempt_success" in line for line in flags(db, TEACHER).stdout.splitlines())


def test_nothing_outside_the_window_and_the_cap_is_24_hours(db):
    got = flags(db, TEACHER, since="now() - interval '3 hours'")
    assert (
        "S1-P1/no_progress" in kinds(got) and len(kinds(got)) == 5
    )  # now includes the 90-minute-old one
    far = flags(db, TEACHER, since="now() - interval '30 days'")
    assert len(kinds(far)) == 5  # never reaches back beyond 24 hours


def test_a_teacher_sees_only_their_own_sessions_flags(db):
    other = flags(db, OTHER_TEACHER)
    assert kinds(other) == ["S1-P1/no_progress", "S1-P1/review"]  # their session at S1, not mine
    assert kinds(flags(db, TEACHER)) != kinds(other)


def test_another_stations_flags_are_not_reachable(db):
    refused = flags(db, TEACHER, station="S2")
    assert refused.returncode and "Not authorized for station" in refused.stderr


def test_only_a_signed_in_teacher_of_the_station_can_read(db):
    assert "Not authorized for station" in flags(db, None).stderr
    anon = db("set role anon; select * from public.read_station_flags('S1', null);", check=False)
    assert anon.returncode and "permission denied" in anon.stderr
    service = db(
        "set role service_role; select * from public.read_station_flags('S1', null);", check=False
    )
    assert service.returncode


def test_no_payload_or_score_is_returned(db):
    got = db(
        f"set role authenticated; select set_config('request.jwt.claims',"
        f'\'{{"sub":"{TEACHER}","role":"authenticated"}}\',false); '
        "select * from public.read_station_flags('S1', null);",
        check=False,
    )
    assert "never returned" not in got.stdout
    columns = db("select string_agg(column_name, ',') from information_schema.columns where false;")
    assert columns.returncode == 0
    header = db(
        f"set role authenticated; select set_config('request.jwt.claims',"
        f'\'{{"sub":"{TEACHER}","role":"authenticated"}}\',false); '
        "select proargnames from pg_proc where proname='read_station_flags';",
        check=False,
    ).stdout
    assert "seat_id" in header and "kind" in header and "payload" not in header
