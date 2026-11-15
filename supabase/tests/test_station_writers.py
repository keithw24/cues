"""One camera per station (migration 1700). Real PostgreSQL, temporary local cluster.

    LC_ALL=en_US.UTF-8 uv run pytest supabase/tests/test_station_writers.py

Never uses DATABASE_URL or hosted credentials. Skipped without initdb/pg_ctl/psql.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase/migrations"
MEMBER = "00000000-0000-4000-8000-0000000000a1"
OUTSIDER = "00000000-0000-4000-8000-0000000000a2"
CAM_A = "00000000-0000-4000-8000-0000000000c1"
CAM_B = "00000000-0000-4000-8000-0000000000c2"


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-station-writers-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55502",
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
            f"-k {directory} -p 55502 -h ''",
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
              insert into auth.users values ('{MEMBER}'),('{OUTSIDER}');
              insert into public.stations(id, name) values ('S1','One'),('S2','Two'),('S3','Three');
              insert into public.station_teachers(station_id, teacher_id) values ('S1','{MEMBER}');
            """)
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def claim(db, station, writer, ttl=10):
    result = db(
        f"set role service_role; select public.claim_station_writer('{station}','{writer}',{ttl});",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def row(db, station, column):
    return db(
        f"select {column} from public.station_writers where station_id='{station}';"
    ).stdout.strip()


def test_the_first_camera_gets_the_station(db):
    got = claim(db, "S1", CAM_A)
    assert got["granted"] is True
    assert row(db, "S1", "writer_id") == CAM_A


def test_a_second_camera_is_refused_and_the_refusal_is_recorded(db):
    assert row(db, "S1", "contested_at") == ""  # nobody has been refused yet
    got = claim(db, "S1", CAM_B)
    assert got["granted"] is False
    assert row(db, "S1", "writer_id") == CAM_A  # the holder is unchanged
    assert row(db, "S1", "contested_at") != ""  # and the dashboard can see the refusal


def test_the_holder_renews_and_stays_the_holder(db):
    for _ in range(3):
        assert claim(db, "S1", CAM_A)["granted"] is True
    assert claim(db, "S1", CAM_B)["granted"] is False  # still refused while the lease is fresh


def test_each_station_has_its_own_holder(db):
    assert claim(db, "S2", CAM_B)["granted"] is True  # CAM_B holds S2 while refused on S1
    assert claim(db, "S2", CAM_A)["granted"] is False


def test_a_crashed_holders_lease_expires_and_the_other_camera_takes_over(db):
    db(
        "update public.station_writers set seen_at = now() - interval '30 seconds' "
        "where station_id='S1';"
    )
    assert claim(db, "S1", CAM_B)["granted"] is True
    assert row(db, "S1", "writer_id") == CAM_B
    assert claim(db, "S1", CAM_A)["granted"] is False  # now A is the one refused


def test_a_camera_that_stops_releases_the_station_at_once(db):
    db(f"set role service_role; select public.release_station_writer('S1','{CAM_B}');")
    assert claim(db, "S1", CAM_A)["granted"] is True  # no waiting for the lease to expire


def test_releasing_someone_elses_lease_does_nothing(db):
    db(f"set role service_role; select public.release_station_writer('S1','{CAM_B}');")
    assert claim(db, "S1", CAM_B)["granted"] is False  # A still holds it


def test_concurrent_claims_have_exactly_one_winner(db):
    writers = [f"00000000-0000-4000-8000-0000000001{n:02d}" for n in range(8)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda w: claim(db, "S3", w)["granted"], writers))
    assert sum(results) == 1


def test_an_unknown_station_is_refused(db):
    result = db(
        f"set role service_role; select public.claim_station_writer('S99','{CAM_A}',10);",
        check=False,
    )
    assert result.returncode and "Station unavailable" in result.stderr


def test_only_the_backend_can_claim_or_release(db):
    for role in ("anon", "authenticated"):
        for call in (
            f"public.claim_station_writer('S1','{CAM_A}',10)",
            f"public.release_station_writer('S1','{CAM_A}')",
        ):
            denied = db(f"set role {role}; select {call};", check=False)
            assert denied.returncode and "permission denied" in denied.stderr
    for privilege in ("INSERT", "UPDATE", "DELETE"):
        assert (
            db(
                f"select has_table_privilege('authenticated','public.station_writers',"
                f"'{privilege}');"
            ).stdout.strip()
            == "f"
        )


def test_teachers_read_only_their_own_stations_row(db):
    def visible(user):
        claims = f'{{"sub":"{user}","role":"authenticated"}}'
        out = db(
            f"set role authenticated; select set_config('request.jwt.claims',"
            f"'{claims}',false); select station_id from public.station_writers "
            "order by station_id;"
        ).stdout.split()
        return [line for line in out if re.fullmatch(r"S\d+", line)]  # drop psql's "SET"

    assert "S1" in visible(MEMBER) and "S2" not in visible(MEMBER)  # S2 is not theirs
    assert visible(OUTSIDER) == []  # a stranger sees nothing
