"""Shared dynamic send/acknowledgement boundary, also used by browser test sends."""

import json
import os
import subprocess
from pathlib import Path

from agent.notifications import NotificationUnavailable
from shared.phone import is_e164


def send_to_teacher(client, config: dict, root: Path, user_id: str, message: str) -> str:
    profiles = (
        client.table("teacher_profiles")
        .select("phone_number")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    rows = (
        client.table("teacher_notification_settings")
        .select("notification_opt_in,notification_phone,photon_project_id,registration_attempt")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    phone = profiles[0].get("phone_number") if profiles else None
    state = rows[0] if rows else {}
    project = config.get("SPECTRUM_PROJECT_ID")
    if not project or not config.get("SPECTRUM_PROJECT_SECRET"):
        raise NotificationUnavailable("Notification configuration unavailable")
    if (
        state.get("notification_opt_in") is not True
        or not is_e164(phone)
        or state.get("notification_phone") != phone
        or state.get("photon_project_id") != project
        or not state.get("registration_attempt")
    ):
        raise NotificationUnavailable("Teacher notification consent unavailable")
    env = dict(os.environ)
    for name in ("SPECTRUM_TEACHER_PHONE", "PHOTON_TOKEN", "DASHBOARD_TOKEN"):
        env.pop(name, None)
    env["CUES_USE_STATIC_TEACHER_PHONE"] = "0"
    for name in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET", "SPECTRUM_SENDER_PHONE"):
        if config.get(name):
            env[name] = config[name]
    try:
        sent = subprocess.run(
            [str(root / "cues/node_modules/.bin/tsx"), str(root / "cues/src/notify.ts")],
            input=json.dumps({"message": message, "destination": phone}),
            capture_output=True,
            text=True,
            env=env,
            timeout=25,
        )
        try:
            result = json.loads(sent.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {}
        outcome = (
            "accepted"
            if sent.returncode == 0 and result.get("accepted") is True
            else (
                "target_not_allowed"
                if result.get("category") == "target_not_allowed"
                else "provider_failure"
            )
        )
    except (subprocess.TimeoutExpired, OSError):
        outcome = "network_failure"
    updated = (
        client.rpc(
            "record_teacher_notification_send",
            {
                "p_user_id": user_id,
                "p_phone": phone,
                "p_attempt": state["registration_attempt"],
                "p_project_id": project,
                "p_result": outcome,
            },
        )
        .execute()
        .data
    )
    if updated is not True:
        raise NotificationUnavailable("Notification consent changed; send result not applied")
    if outcome == "accepted":
        return "registered"
    if outcome == "target_not_allowed":
        return "pending"
    raise NotificationUnavailable(f"Notification send failed: {outcome}")


def main():
    """Trusted server subprocess: identity arrives only from verified server auth."""
    import sys

    from supabase import create_client

    try:
        payload = json.load(sys.stdin)
        config = payload["config"]
        client = create_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
        status = send_to_teacher(
            client,
            config,
            Path(payload["root"]),
            payload["user_id"],
            "Cues notifications are connected.",
        )
        print(json.dumps({"status": status}))
    except Exception:
        print(json.dumps({"error": "Notification test unavailable. Check consent and activation."}))
        sys.exit(1)


if __name__ == "__main__":
    main()
