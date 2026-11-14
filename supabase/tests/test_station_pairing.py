"""Optional real-Postgres tests: pytest supabase/tests/test_station_pairing.py.

Uses only a fresh temporary local cluster, never DATABASE_URL or hosted credentials.
"""

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-pairing-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55497",
            "PGDATABASE": "postgres",
            "PGUSER": os.environ.get("USER", ""),
        }

        def run(*args, **kwargs):
            return subprocess.run(args, capture_output=True, text=True, check=True, **kwargs)

        run("initdb", "-D", data, "-A", "trust", "--no-locale")
        run(
            "pg_ctl",
            "-D",
            data,
            "-l",
            str(Path(directory) / "postgres.log"),
            "-o",
            f"-k {directory} -p 55497 -h ''",
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
                select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
              create function auth.role() returns text language sql as $$
                select nullif(current_setting('request.jwt.claim.role',true),'') $$;
              create table public.stations(id text primary key);
              insert into public.stations values ('S1'),('S2');
              create table public.station_teachers(station_id text references public.stations,
                teacher_id uuid references auth.users, primary key(station_id,teacher_id));
              alter table public.station_teachers enable row level security;
              revoke all on public.station_teachers from public, anon, authenticated;
              grant all on public.station_teachers to service_role;
              create table public.sessions(id integer primary key, teacher_id uuid);
              insert into public.sessions values (1,null);
            """)
            sql(f"insert into auth.users values ('{A}'),('{B}');")
            sql((ROOT / "supabase/migrations/20261114000800_station_pairing.sql").read_text())
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def issue(db):
    return db("select code from public.issue_station_pairing_code('S1');").stdout.strip()


def redeem(db, code, user=A):
    return db(
        f"set role authenticated; set request.jwt.claim.role='authenticated'; "
        f"set request.jwt.claim.sub='{user}'; "
        f"select * from public.redeem_station_pairing_code('{code}');",
        check=False,
    )


def test_valid_normalized_code_and_repeat_membership(db):
    for _ in range(2):
        code = issue(db)
        assert redeem(db, " " + code.lower().replace("-", " ") + " ").returncode == 0
        assert (
            db(
                f"select used_by from public.station_pairing_codes where code_hash="
                f"public.station_pairing_code_hash('{code}');"
            ).stdout.strip()
            == A
        )
    assert (
        db(f"select count(*) from public.station_teachers where teacher_id='{A}';").stdout.strip()
        == "1"
    )
    assert db("select teacher_id is null from public.sessions where id=1;").stdout.strip() == "t"


def test_invalid_expired_used_and_unauthenticated(db):
    code = issue(db)
    assert redeem(db, code).returncode == 0
    for bad in (code, "wrong"):
        result = redeem(db, bad)
        assert result.returncode != 0 and "Invalid or unavailable pairing code" in result.stderr
    expired = issue(db)
    db(
        f"update public.station_pairing_codes set created_at=now()-interval '1 day',"
        " expires_at=now()-interval '1 hour' "
        f"where code_hash=public.station_pairing_code_hash('{expired}');"
    )
    assert "Invalid or unavailable pairing code" in redeem(db, expired).stderr
    fresh = issue(db)
    assert db(
        f"set role anon; select * from public.redeem_station_pairing_code('{fresh}');", False
    ).returncode
    assert redeem(db, fresh, "").returncode


def test_permissions_and_fixed_rpc_identity(db):
    for role in ("anon", "authenticated"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert (
                db(
                    f"select has_table_privilege('{role}',"
                    f"'public.station_pairing_codes','{privilege}');"
                ).stdout.strip()
                == "f"
            )
        assert (
            db(
                f"select has_function_privilege('{role}',"
                "'public.issue_station_pairing_code(text,integer)','EXECUTE');"
            ).stdout.strip()
            == "f"
        )
    assert (
        db(
            "select has_table_privilege('authenticated','public.station_teachers','INSERT');"
        ).stdout.strip()
        == "f"
    )
    assert (
        db(
            "select has_table_privilege('service_role','public.station_pairing_codes','INSERT');"
        ).stdout.strip()
        == "t"
    )
    assert (
        db(
            "select pronargs from pg_proc "
            "where oid='public.redeem_station_pairing_code(text)'::regprocedure;"
        ).stdout.strip()
        == "1"
    )
    assert (
        db("select count(*) from public.station_teachers where station_id='S2';").stdout.strip()
        == "0"
    )


def test_concurrent_redemption_has_one_winner(db):
    code = issue(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda user: redeem(db, code, user), [A, B]))
    assert sorted(result.returncode == 0 for result in results) == [False, True]
    assert "Invalid or unavailable pairing code" in next(r.stderr for r in results if r.returncode)
