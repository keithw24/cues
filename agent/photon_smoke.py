"""One direct test send to the configured session owner's Supabase profile."""

import json
import os
import subprocess

from dotenv import load_dotenv

from shared.supabase_client import REPO_ROOT, get_client


def main():
    load_dotenv(REPO_ROOT / ".env")
    session_id = os.environ.get("CUES_SESSION_ID")
    client = get_client()
    if not session_id or client is None:
        raise SystemExit("Configure CUES_SESSION_ID and backend Supabase credentials.")
    try:
        rows = client.table("sessions").select("teacher_id").eq("id", session_id).execute().data
        owner = rows[0].get("teacher_id") if rows else None
        if not owner:
            raise SystemExit("Configured session has no teacher owner; no message sent.")
        profiles = (
            client.table("teacher_profiles")
            .select("phone_number")
            .eq("user_id", owner)
            .execute()
            .data
        )
        phone = profiles[0].get("phone_number") if profiles else None
        if not phone:
            raise SystemExit("Session owner has no profile phone; no message sent.")
    except SystemExit:
        raise
    except Exception:
        raise SystemExit("Supabase teacher destination lookup failed; no message sent.") from None
    env = dict(os.environ)
    env.pop("SPECTRUM_TEACHER_PHONE", None)
    env["CUES_USE_STATIC_TEACHER_PHONE"] = "0"
    env["CUES_SPECTRUM_DEBUG"] = "1"
    try:
        result = subprocess.run(
            [str(REPO_ROOT / "cues/node_modules/.bin/tsx"), "src/notify.ts"],
            cwd=REPO_ROOT / "cues",
            env=env,
            input=json.dumps({"message": "Cues test notification", "destination": phone}),
            text=True,
            capture_output=True,
            timeout=25,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("Spectrum send timed out; acceptance unknown.") from None
    # Only surface the sender's sanitized diagnostics, never raw SDK output.
    for line in result.stderr.splitlines():
        try:
            diagnostic = json.loads(line)
        except ValueError:
            continue
        if isinstance(diagnostic, dict) and diagnostic.get("cuesNotification") is True:
            print(json.dumps(diagnostic))
    if result.returncode or not result.stdout.strip().endswith('{"accepted":true}'):
        raise SystemExit("Spectrum did not acknowledge the profile-phone test message.")
    print("Accepted: test message sent to the configured session owner profile phone.")


if __name__ == "__main__":
    main()
