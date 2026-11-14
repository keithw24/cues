"""Replay every migration on temporary local PostgreSQL with minimal Auth stubs.

Never uses hosted credentials. Supabase-specific Auth/Realtime services are not
emulated; this verifies SQL ordering, dependencies and final database definitions.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def test_full_migration_chain():
    if not all(shutil.which(name) for name in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    root = Path(__file__).resolve().parents[2]
    files = sorted((root / "supabase/migrations").glob("*.sql"))
    versions = [file.name.split("_")[0] for file in files]
    assert len(versions) == len(set(versions))
    with tempfile.TemporaryDirectory(prefix="cues-full-replay-") as directory:
        data = str(Path(directory) / "data")
        env = {
            **os.environ,
            "PGHOST": directory,
            "PGPORT": "55496",
            "PGDATABASE": "postgres",
            "PGUSER": os.environ.get("USER", ""),
        }

        def command(*args):
            return subprocess.run(args, capture_output=True, text=True, check=True)

        def sql(value):
            result = subprocess.run(
                ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1"],
                env=env,
                input=value,
                text=True,
                capture_output=True,
            )
            assert result.returncode == 0, result.stderr
            return result.stdout.strip()

        command("initdb", "-D", data, "-A", "trust", "--no-locale")
        command(
            "pg_ctl",
            "-D",
            data,
            "-l",
            str(Path(directory) / "postgres.log"),
            "-o",
            f"-k {directory} -p 55496 -h ''",
            "-w",
            "start",
        )
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
            for file in files:
                try:
                    sql(file.read_text())
                except AssertionError as error:
                    raise AssertionError(f"{file.name}: {error}") from error
            assert sql("select to_regclass('public.station_pairing_codes') is not null;") == "t"
            assert (
                sql("select has_table_privilege('authenticated','public.sessions','INSERT');")
                == "f"
            )
            assert (
                sql(
                    "select has_table_privilege('authenticated',"
                    "'public.station_teachers','INSERT');"
                )
                == "f"
            )
            assert (
                sql(
                    "select count(*) from pg_proc where oid in "
                    "('public.start_station_activity(text,text,uuid,integer)'::regprocedure,"
                    "'public.redeem_station_pairing_code(text)'::regprocedure);"
                )
                == "2"
            )
            sql("""
              insert into auth.users values ('00000000-0000-4000-8000-000000000009');
              insert into public.teacher_profiles(user_id,phone_number) values
                ('00000000-0000-4000-8000-000000000009','+12025550101');
              select * from public.prepare_teacher_notification_registration(
                '00000000-0000-4000-8000-000000000009',true,'Ada','Lovelace','project');
              create table old_attempt as select registration_attempt
                from public.teacher_notification_settings;
            """)
            call = "public.record_teacher_notification_send('00000000-0000-4000-8000-000000000009',"
            assert (
                sql(f"select {call} '+12025550101',gen_random_uuid(),'project','accepted');") == "f"
            )
            assert (
                sql(
                    f"select {call} '+12025550102',"
                    "(select registration_attempt from old_attempt),'project','accepted');"
                )
                == "f"
            )
            for outcome, status in [
                ("target_not_allowed", "registering"),
                ("accepted", "registered"),
            ]:
                assert (
                    sql(
                        f"select {call} '+12025550101',"
                        f"(select registration_attempt from old_attempt),'project','{outcome}');"
                    )
                    == "t"
                )
                assert (
                    sql(
                        "select photon_registration_status "
                        "from public.teacher_notification_settings;"
                    )
                    == status
                )
            assert (
                sql(
                    "select photon_registered_at is not null and photon_registration_error is null "
                    "from public.teacher_notification_settings;"
                )
                == "t"
            )
            assert (
                sql(
                    "select has_function_privilege('authenticated',"
                    "'public.record_teacher_notification_send(uuid,text,uuid,text,text)','EXECUTE');"
                )
                == "f"
            )
            # Revocation/reconsent creates a new attempt on the same phone.
            sql("""
              select * from public.prepare_teacher_notification_registration(
                '00000000-0000-4000-8000-000000000009',false,'Ada','Lovelace','project');
              select * from public.prepare_teacher_notification_registration(
                '00000000-0000-4000-8000-000000000009',true,'Ada','Lovelace','project');
            """)
            assert (
                sql(
                    f"select {call} '+12025550101',"
                    "(select registration_attempt from old_attempt),'project','accepted');"
                )
                == "f"
            )
            assert (
                sql("select photon_registration_status from public.teacher_notification_settings;")
                == "registering"
            )
            sql("""
              update public.teacher_notification_settings set
                photon_registration_status='registered',photon_registered_at=now();
              update public.teacher_profiles set phone_number='+12025550102';
            """)
            assert (
                sql("select notification_opt_in from public.teacher_notification_settings;") == "f"
            )
            assert (
                sql(
                    f"select {call} '+12025550101',"
                    "(select registration_attempt from old_attempt),'project','accepted');"
                )
                == "f"
            )
            assert (
                sql("select photon_registration_status from public.teacher_notification_settings;")
                == "unregistered"
            )
            assert (
                sql(
                    "select registration_attempt is null from public.teacher_notification_settings;"
                )
                == "t"
            )
            assert (
                sql(
                    "select has_table_privilege('authenticated',"
                    "'public.teacher_notification_settings','UPDATE');"
                )
                == "f"
            )
            assert (
                sql(
                    "select has_function_privilege('authenticated',"
                    "'public.prepare_teacher_notification_registration(uuid,boolean,text,text,text)',"
                    "'EXECUTE');"
                )
                == "f"
            )
            sql("""
              insert into public.activities(id,name,check_type,no_progress_seconds,config)
                values('progress_test','Progress test','rule',30,'{}');
              insert into public.stations(id,name) values('progress_station','Progress station');
              insert into public.seats(id,station_id,display_name,is_simulated)
                values('progress_seat','progress_station','Simulated',true);
              insert into public.sessions(id,station_id,current_activity_id,revision)
                values('00000000-0000-4000-8000-000000000012','progress_station','progress_test',0);
              insert into public.seat_state(seat_id,session_id,activity_id,status,
                                            updated_at,session_revision)
                values('progress_seat','00000000-0000-4000-8000-000000000012','progress_test',
                       'in_progress','2026-11-14T23:00:00Z',0);
            """)
            progress_call = (
                "select public.publish_task_progress('progress_seat',"
                "'00000000-0000-4000-8000-000000000012','progress_test',"
            )
            payload = '\'{"trend":"stalled","stalled_seconds":6,"recent":[]}\'::jsonb);'
            assert sql(progress_call + "0,'2026-11-14T23:00:00Z'," + payload) == "t"
            assert sql(progress_call + "1,'2026-11-14T23:00:00Z'," + payload) == "f"
            assert sql(progress_call + "0,'2026-11-14T22:59:59Z'," + payload) == "f"
            sql("update public.sessions set ended_at=now() where station_id='progress_station';")
            assert sql(progress_call + "0,'2026-11-14T23:00:00Z'," + payload) == "f"
            assert (
                sql(
                    "select has_function_privilege('authenticated',"
                    "'public.publish_task_progress(text,uuid,text,integer,timestamptz,jsonb)',"
                    "'EXECUTE');"
                )
                == "f"
            )
        finally:
            command("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")
