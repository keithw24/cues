"""Intervention approval (migration 1800). Real PostgreSQL, temporary local cluster.

    LC_ALL=en_US.UTF-8 uv run pytest supabase/tests/test_interventions.py

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
MIGRATION = "20261114001800_interventions.sql"
TEACHER = "00000000-0000-4000-8000-0000000000e1"
STRANGER = "00000000-0000-4000-8000-0000000000e2"
S_RUN = "00000000-0000-4000-8000-0000000000f1"  # S1, running
S_OTHER = "00000000-0000-4000-8000-0000000000f3"  # S2, running, another teacher


@pytest.fixture(scope="module")
def db():
    if not all(shutil.which(tool) for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL tools unavailable")
    with tempfile.TemporaryDirectory(prefix="cues-interventions-") as directory:
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
            files = sorted(MIGRATIONS.glob("*.sql"))
            assert MIGRATION in [f.name for f in files]
            for file in files:
                if file.name < MIGRATION:
                    sql(file.read_text())
            sql(f"""
              insert into auth.users values ('{TEACHER}'),('{STRANGER}');
              insert into public.stations(id, name) values ('S1','One'),('S2','Two');
              insert into public.seats(id, station_id, display_name, is_simulated) values
                ('S1-P1','S1','Person 1',true),('S1-P2','S1','Person 2',true),
                ('S2-P1','S2','Person 1',true);
              insert into public.station_teachers(station_id, teacher_id) values ('S1','{TEACHER}');
              insert into public.activities(id, name, check_type, no_progress_seconds, config)
                values ('raise_hand','Raise your hand','rule',30,'{{}}'),
                       ('thumbs_up','Thumbs up','gesture',30,'{{}}')
                on conflict (id) do nothing;
              insert into public.sessions(id, station_id, current_activity_id, teacher_id)
                values ('{S_RUN}','S1','raise_hand','{TEACHER}'),
                       ('{S_OTHER}','S2','raise_hand','{STRANGER}');
            """)
            sql((MIGRATIONS / MIGRATION).read_text())
            yield sql
        finally:
            run("pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


MENU = (
    "repeat_instruction",
    "show_example",
    "model_task",
    "smaller_steps",
    "offer_break",
    "adult_check_in",
)


def review(seat, n, suggested=None, status="pending"):
    column = ", suggested_intervention" if suggested else ""
    value = f", '{suggested}'" if suggested else ""
    # Reviews are always created pending; the guard trigger allows one transition afterwards.
    close = (
        f"update public.teacher_reviews set status='{status}', resolved_at=clock_timestamp() "
        f"where id='{rid(n)}';"
        if status != "pending"
        else ""
    )
    return f"""
      insert into public.teacher_reviews(id, created_at, session_id, seat_id, activity_id,
        priority, evaluation, decision, rationale, evidence_used{column})
      values ('{rid(n)}', now() - interval '5 minutes', '{S_RUN}', '{seat}',
        'raise_hand', 'normal',
        jsonb_build_object('session_id','{S_RUN}','seat_id','{seat}','activity_id','raise_hand',
          'escalation', jsonb_build_object('priority','normal','should_evaluate', true),
          'progress', jsonb_build_object('trend','stalled'), 'n', {n}),
        'teacher_review_warranted', 'Stalled.', '["current_progress"]'{value});
      {close}"""


def rid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


def scalar(db, query):
    return db(query).stdout.strip()


def as_user(db, user, statement):
    claims = f'{{"sub":"{user}","role":"authenticated"}}' if user else "{}"
    return db(
        f"set role authenticated; select set_config('request.jwt.claims','{claims}',false); "
        + statement,
        check=False,
    )


def approve(db, user, n, action=None):
    arg = f", '{action}'" if action else ""
    return as_user(
        db, user, f"select action from public.approve_review_intervention('{rid(n)}'{arg});"
    )


def status_of(db, n):
    return scalar(db, f"select status from public.teacher_reviews where id='{rid(n)}';")


def test_a_suggestion_is_stored_only_from_the_menu(db):
    db(review("S1-P1", 1, "offer_break"))
    assert (
        scalar(
            db, f"select suggested_intervention from public.teacher_reviews where id='{rid(1)}';"
        )
        == "offer_break"
    )
    bad = db(review("S1-P2", 2, "x_not_on_menu"), check=False)
    assert bad.returncode != 0


def test_approving_the_suggestion_confirms_the_review_and_records_it(db):
    db(review("S1-P10", 10, "show_example"))
    done = approve(db, TEACHER, 10)
    assert done.returncode == 0, done.stderr
    assert "show_example" in done.stdout
    assert status_of(db, 10) == "confirmed"
    assert (
        scalar(
            db,
            "select count(*) from public.interventions "
            f"where review_id='{rid(10)}' and approved_at is not null;",
        )
        == "1"
    )


def test_the_teacher_may_pick_another_item_instead(db):
    db(review("S1-P11", 11, "show_example"))
    done = approve(db, TEACHER, 11, "adult_check_in")
    assert done.returncode == 0, done.stderr
    assert (
        scalar(db, f"select action from public.interventions where review_id='{rid(11)}';")
        == "adult_check_in"
    )


def test_a_review_with_no_suggestion_needs_a_choice(db):
    db(review("S1-P12", 12))
    nothing = approve(db, TEACHER, 12)
    assert nothing.returncode != 0 and "choose an approved intervention" in nothing.stderr
    assert status_of(db, 12) == "pending"
    assert approve(db, TEACHER, 12, "model_task").returncode == 0


def test_an_action_outside_the_menu_is_refused(db):
    db(review("S1-P13", 13, "offer_break"))
    refused = approve(db, TEACHER, 13, "change_the_task")
    assert refused.returncode != 0
    assert status_of(db, 13) == "pending"


def test_only_the_owning_signed_in_teacher_can_approve(db):
    db(review("S1-P14", 14, "offer_break"))
    assert approve(db, STRANGER, 14).returncode != 0
    assert approve(db, None, 14).returncode != 0
    assert status_of(db, 14) == "pending"
    anon = db(
        f"set role anon; select * from public.approve_review_intervention('{rid(14)}');",
        check=False,
    )
    assert anon.returncode != 0


def test_one_approval_per_review(db):
    db(review("S1-P15", 15, "offer_break"))
    assert approve(db, TEACHER, 15).returncode == 0
    again = approve(db, TEACHER, 15, "model_task")
    assert again.returncode != 0 and "already approved" in again.stderr


def test_closed_reviews_cannot_be_approved(db):
    for n, state in ((16, "dismissed"), (17, "expired")):
        db(review(f"S1-P{n}", n, "offer_break", status=state))
        refused = approve(db, TEACHER, n)
        assert refused.returncode != 0 and "review is closed" in refused.stderr


def test_an_already_confirmed_review_can_still_get_its_approval(db):
    db(review("S1-P18", 18, "offer_break", status="confirmed"))
    assert approve(db, TEACHER, 18).returncode == 0
    assert status_of(db, 18) == "confirmed"


def test_teachers_read_their_own_approvals_only(db):
    mine = as_user(db, TEACHER, "select count(*) from public.interventions;")
    theirs = as_user(db, STRANGER, "select count(*) from public.interventions;")
    assert int(mine.stdout.strip().splitlines()[-1]) >= 3
    assert theirs.stdout.strip().splitlines()[-1] == "0"


def test_teachers_cannot_write_interventions_directly(db):
    direct = as_user(
        db,
        TEACHER,
        "insert into public.interventions(id, review_id, action, approved_at) "
        f"values (gen_random_uuid(), '{rid(1)}', 'offer_break', now());",
    )
    assert direct.returncode != 0
