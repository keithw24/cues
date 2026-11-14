"""Offline regression checks for diagnostic precedence and truthful UI classification."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ui_audit", ROOT / "scripts/ui-audit.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


def feature(data, name):
    return next(row for row in data["features"] if row["feature"] == name)


def test_env_precedence_and_example_not_loaded(tmp_path):
    (tmp_path / "web").mkdir()
    for name, text in {
        "web/.env": "VALUE=base\n",
        "web/.env.development": "VALUE=dev\n",
        "web/.env.local": "VALUE=local\n",
        "web/.env.development.local": "VALUE=devlocal\n",
        "web/.env.example": "VALUE=example\nTEMPLATE_ONLY=1\n",
        ".env": "VALUE=launcher\n",
    }.items():
        (tmp_path / name).write_text(text)
    assert ui.configuration(tmp_path, {})[0]["VALUE"] == "launcher"
    assert ui.configuration(tmp_path, {}, direct_next=True)[0]["VALUE"] == "devlocal"
    values, origins = ui.configuration(tmp_path, {"VALUE": "process"})
    assert values["VALUE"] == "process" and origins["VALUE"] == "process environment"
    assert "TEMPLATE_ONLY" not in values


def test_flag_override_reports_hidden_reason_and_never_outputs_secrets():
    report = ui.audit(
        process={
            "CUES_FLAG_WEB_TEACHER_REVIEWS": "0",
            "SUPABASE_SERVICE_ROLE_KEY": "never-print-this-secret",
        }
    )
    row = feature(report, "Pending review queue")
    assert row["status"] == "hidden by flag"
    assert "process environment" in row["reason"]
    assert "never-print-this-secret" not in json.dumps(report)


def test_private_flag_precedes_public_alias():
    report = ui.audit(
        process={
            "CUES_FLAG_WEB_TEACHER_REVIEWS": "0",
            "NEXT_PUBLIC_CUES_FLAG_WEB_TEACHER_REVIEWS": "1",
        }
    )
    assert feature(report, "Pending review queue")["status"] == "hidden by flag"


def test_missing_mount_is_not_claimed_rendered(monkeypatch):
    original = ui.source

    def read(root, path):
        text = original(root, path)
        return (
            text.replace("<DemoNotifications", "<OtherComponent")
            if path.endswith("teacher-profile-form.tsx")
            else text
        )

    monkeypatch.setattr(ui, "source", read)
    row = feature(ui.audit(process={}), "Send test notification")
    assert row["code"] is True
    assert row["status"] == "unmounted/changed"


def test_hosted_catalog_is_required_not_just_vision_capability():
    data = ui.audit(process={"CUES_FLAG_WEB_DASHBOARD": "1", "CUES_FLAG_WEB_SESSION_CONTROLS": "1"})
    # Avoid dependence on credentials/config in the checkout for this classification.
    for row in data["features"]:
        if "activity_id" in row:
            row["status"] = "data-dependent"
    ui.apply_catalog(
        data,
        {
            "activity_ids": ["raise_hand"],
            "supported_ids": ["raise_hand", "thumbs_up", "custom_gesture_01"],
            "station_runtime_present": True,
        },
    )
    assert feature(data, "Raise hand activity")["status"] == "catalog option (conditional)"
    assert feature(data, "Thumbs up activity")["status"] == "hidden by catalog"
    assert "public.activities" in feature(data, "Custom gesture activity")["reason"]


def test_placeholder_and_creation_gaps_are_not_reported_as_functional_ui():
    data = ui.audit(process={})
    assert feature(data, "Notifications sidebar page")["status"] == "placeholder"
    assert feature(data, "Custom gesture creation/recording UI")["code"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://user:secret@localhost",
        "http://localhost/?token=secret",
        "file:///tmp/test",
    ],
)
def test_runtime_rejects_nonlocal_or_credential_urls(url):
    with pytest.raises(ValueError):
        ui.runtime_checks(url, [])
