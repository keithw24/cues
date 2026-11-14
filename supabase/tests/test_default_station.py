"""Default station per teacher (migration 1100). Real PostgreSQL, temporary local cluster.

    uv run pytest supabase/tests/test_default_station.py

Never uses DATABASE_URL or hosted credentials. Skipped when initdb/pg_ctl/psql are missing.
Migrations up to 1000 are replayed, existing data is seeded (Keith assigned to S1, with
historical sessions), and only then is migration 1100 applied, so the backfill is tested.
"""

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase/migrations"
DEFAULT_STATION_MIGRATION = "20261114001100_default_station.sql"
KEITH = "00000000-0000-4000-8000-0000000000a1"
MICHELLE = "00000000-0000-4000-8000-0000000000a2"
EVAN = "00000000-0000-4000-8000-0000000000a3"
NEW_TEACHER = "00000000-0000-4000-8000-0000000000a4"
OLD_SESSION = "00000000-0000-4000-8000-0000000000b1"


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-default-station-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55498",
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
            f"-k {directory} -p 55498 -h ''",
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
            assert DEFAULT_STATION_MIGRATION in [f.name for f in files]
            for file in files:
                if file.name < DEFAULT_STATION_MIGRATION:
                    sql(file.read_text())
            # Existing production-like data: one teacher (Keith) assigned to S1 with history.
            sql(f"""
              insert into auth.users values ('{KEITH}'),('{MICHELLE}'),('{EVAN}'),('{NEW_TEACHER}');
              insert into public.activities(id, name, check_type, no_progress_seconds, config)
                values ('raise_hand', 'Raise your hand', 'rule', 30, '{{}}');
              insert into public.stations(id, name) values ('S1', 'Demo station');
              insert into public.station_teachers(station_id, teacher_id) values ('S1', '{KEITH}');
              insert into public.sessions(id, station_id, current_activity_id, teacher_id, ended_at)
                values ('{OLD_SESSION}', 'S1', 'raise_hand', null, now());
            """)
            sql((MIGRATIONS / DEFAULT_STATION_MIGRATION).read_text())
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def as_teacher(db, user, statement):
    """Run a statement as a signed-in browser user (the `authenticated` role)."""
    claims = f'{{"sub":"{user}","role":"authenticated"}}' if user else "{}"
    return db(
        f"set role authenticated; select set_config('request.jwt.claims','{claims}',false); "
        + statement,
        check=False,
    )


def default_station(db, user):
    result = as_teacher(db, user, "select public.get_or_create_my_default_station();")
    assert result.returncode == 0, result.stderr
    import json

    return json.loads(result.stdout.strip().splitlines()[-1])


def count(db, query):
    return int(db(query).stdout.strip())


# 1. An existing teacher with S1 gets S1 (their one assignment becomes the default).
def test_existing_teacher_keeps_s1_and_it_is_marked_default(db):
    assert (
        db(
            f"select is_default from public.station_teachers "
            f"where teacher_id='{KEITH}' and station_id='S1';"
        ).stdout.strip()
        == "t"
    )
    got = default_station(db, KEITH)
    assert got == {"station_id": "S1", "name": "Demo station", "created": False}
    assert count(db, "select count(*) from public.stations;") == 1  # nothing was created


# 2. A new teacher with no station gets a newly created one, owned by them.
def test_new_teacher_gets_a_new_station(db):
    got = default_station(db, MICHELLE)
    assert got["station_id"] == "S2" and got["created"] is True
    assert (
        db(
            f"select is_default from public.station_teachers "
            f"where teacher_id='{MICHELLE}' and station_id='S2';"
        ).stdout.strip()
        == "t"
    )
    # Person metadata so the dashboard can read this station's people.
    seats = db("select string_agg(id, ',' order by id) from public.seats where station_id='S2';")
    assert seats.stdout.strip() == "S2-P1,S2-P2,S2-P3,S2-P4"
    assert (
        count(db, f"select count(*) from public.station_teachers where teacher_id='{KEITH}';") == 1
    )


# 3. Later calls return the same station and create nothing.
def test_repeat_calls_return_the_same_station(db):
    stations = count(db, "select count(*) from public.stations;")
    for _ in range(3):
        got = default_station(db, MICHELLE)
        assert got["station_id"] == "S2" and got["created"] is False
    assert count(db, "select count(*) from public.stations;") == stations


# 4. A second new teacher gets a different station.
def test_second_teacher_gets_a_different_station(db):
    got = default_station(db, EVAN)
    assert got["station_id"] not in ("S1", "S2") and got["created"] is True
    assert got["station_id"] == "S3"


# 5. Concurrent first calls never create duplicate defaults or colliding station ids.
def test_concurrent_first_calls_create_one_default(db):
    def call(_):
        return default_station(db, NEW_TEACHER)

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(call, range(8)))
    assert len({r["station_id"] for r in results}) == 1
    assert sum(r["created"] for r in results) == 1
    assert (
        count(
            db,
            f"select count(*) from public.station_teachers "
            f"where teacher_id='{NEW_TEACHER}' and is_default;",
        )
        == 1
    )
    assert (
        count(db, f"select count(*) from public.station_teachers where teacher_id='{NEW_TEACHER}';")
        == 1
    )


def test_concurrent_calls_by_different_teachers_get_distinct_stations(db):
    ids = [f"00000000-0000-4000-8000-0000000001{n:02d}" for n in range(6)]
    db("insert into auth.users values " + ",".join(f"('{i}')" for i in ids) + ";")
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda u: default_station(db, u)["station_id"], ids))
    assert len(set(results)) == 6  # no two teachers share a new station


# 6. Unauthenticated callers are rejected.
def test_unauthenticated_callers_are_rejected(db):
    call = "select public.get_or_create_my_default_station();"
    anonymous = db(f"set role anon; {call}", check=False)
    assert anonymous.returncode and "permission denied" in anonymous.stderr
    no_user = as_teacher(db, None, call)
    assert no_user.returncode and "Authentication required" in no_user.stderr
    service = db(f"set role service_role; {call}", check=False)
    assert service.returncode  # the service role has no end user to resolve a station for


# 7. The browser cannot name a teacher or a station owner.
def test_browser_cannot_choose_the_teacher_or_assign_ownership(db):
    # The function takes no parameters, so there is nowhere to pass a teacher UUID.
    assert (
        count(
            db,
            "select pronargs from pg_proc "
            "where oid = 'public.get_or_create_my_default_station()'::regprocedure;",
        )
        == 0
    )
    spoof = as_teacher(
        db, MICHELLE, f"select public.get_or_create_my_default_station('{KEITH}'::uuid);"
    )
    assert spoof.returncode  # no such function
    # Memberships and the default marker are not writable from the browser.
    for statement in (
        f"insert into public.station_teachers(station_id, teacher_id) values ('S1','{MICHELLE}');",
        f"update public.station_teachers set is_default = true where teacher_id='{MICHELLE}';",
        "update public.station_teachers set is_default = false;",
    ):
        assert as_teacher(db, MICHELLE, statement).returncode
    # Each caller only ever gets their own station.
    assert default_station(db, KEITH)["station_id"] == "S1"
    assert default_station(db, MICHELLE)["station_id"] == "S2"


# 8. Start Session creates a NEW session on the resolved default station, owned by the caller.
def test_start_session_uses_the_default_station_and_owns_it(db):
    station = default_station(db, MICHELLE)["station_id"]
    stations = count(db, "select count(*) from public.stations;")
    first = as_teacher(
        db, MICHELLE, f"select public.start_station_activity('{station}','raise_hand',null,null);"
    )
    assert first.returncode == 0, first.stderr
    import json

    session = json.loads(first.stdout.strip().splitlines()[-1])
    assert session["station_id"] == "S2" and session["teacher_id"] == MICHELLE
    ended = as_teacher(
        db,
        MICHELLE,
        f"select public.end_station_session('{station}','{session['id']}',{session['revision']});",
    )
    assert ended.returncode == 0, ended.stderr
    second = as_teacher(
        db, MICHELLE, f"select public.start_station_activity('{station}','raise_hand',null,null);"
    )
    again = json.loads(second.stdout.strip().splitlines()[-1])
    assert again["id"] != session["id"]  # a NEW session...
    assert again["station_id"] == "S2" and again["teacher_id"] == MICHELLE  # ...same station
    assert count(db, "select count(*) from public.stations;") == stations  # no new station
    # Keith cannot use Michelle's station.
    other = as_teacher(
        db, KEITH, "select public.start_station_activity('S2','raise_hand',null,null);"
    )
    assert other.returncode and "Not authorized for station" in other.stderr


# 9. Historical sessions are untouched by the migration and the new calls.
def test_historical_sessions_are_not_claimed(db):
    row = db(
        f"select station_id, teacher_id is null, ended_at is not null "
        f"from public.sessions where id='{OLD_SESSION}';"
    ).stdout.strip()
    assert row == "S1|t|t"
    assert (
        count(
            db,
            "select count(*) from public.sessions "
            f"where id='{OLD_SESSION}' and teacher_id is not null;",
        )
        == 0
    )


# 10. Station pairing still works and does not disturb anyone's default.
def test_station_pairing_still_works_and_keeps_the_default(db):
    code = db("select code from public.issue_station_pairing_code('S1');").stdout.strip()
    redeemed = as_teacher(
        db, MICHELLE, f"select * from public.redeem_station_pairing_code('{code}');"
    )
    assert redeemed.returncode == 0, redeemed.stderr
    memberships = db(
        f"select string_agg(station_id || ':' || is_default::text, ',' order by station_id) "
        f"from public.station_teachers where teacher_id='{MICHELLE}';"
    ).stdout.strip()
    assert memberships == "S1:false,S2:true"  # paired to S1, still defaulting to S2
    assert default_station(db, MICHELLE)["station_id"] == "S2"


def test_teacher_with_several_assignments_and_no_default_gets_their_own_station(db):
    teacher = "00000000-0000-4000-8000-0000000002a1"
    db(
        f"""insert into auth.users values ('{teacher}');
        insert into public.station_teachers(station_id, teacher_id) values
          ('S1','{teacher}'),('S2','{teacher}');"""
    )
    got = default_station(db, teacher)
    assert got["created"] is True and got["station_id"] not in ("S1", "S2")
    assert (
        count(db, f"select count(*) from public.station_teachers where teacher_id='{teacher}';")
        == 3  # the paired memberships are kept
    )
