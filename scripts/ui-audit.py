"""Read-only, Cues-specific UI inventory; no browser/DOM or authentication claims.

Run: uv run python scripts/ui-audit.py [--runtime --base-url http://localhost:3000]
Optional --hosted-catalog reads only activity IDs/station capabilities with backend
credentials. Nothing sends messages, changes flags, signs in, or writes to Supabase.
The inventory is intentionally curated: source anchors fail closed when code moves.
"""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def source(root, path):
    file = root / path
    return file.read_text() if file.is_file() else ""


def configuration(root, process, direct_next=False):
    """Next dev precedence; scripts additionally inherit root .env from agent.dev."""
    values, origins = {}, {}
    node_env = process.get("NODE_ENV", "development")
    # Low to high priority. Next ignores .env.local in test mode.
    files = ["web/.env", f"web/.env.{node_env}"]
    if node_env != "test":
        files.append("web/.env.local")
    files.append(f"web/.env.{node_env}.local")
    if not direct_next:
        files.append(".env")
    for path in files:
        for key, value in dotenv_values(root / path, interpolate=False).items():
            if value is not None:
                values[key], origins[key] = value, path
    for key, value in process.items():
        values[key], origins[key] = value, "process environment"
    return values, origins


def audit(root=ROOT, process=None, direct_next=False):
    registry = json.loads(source(root, "flags.json"))
    env, origins = configuration(root, os.environ if process is None else process, direct_next)
    flags = {}
    for name, entry in registry.items():
        key = "CUES_FLAG_" + name.upper().replace(".", "_")
        selected = key if key in env else "NEXT_PUBLIC_" + key
        raw = env.get(selected)
        value = (
            entry["default"]
            if raw is None
            else (True if raw in ("1", "true") else False if raw in ("0", "false") else None)
        )
        flags[name] = {
            "default": entry["default"],
            "effective": value,
            "source": origins.get(selected, "flags.json"),
            "key": selected,
        }

    features = []
    dashboard = "web/components/dashboard.tsx"
    controls = "web/components/session-controls.tsx"
    profile = "web/components/teacher-profile-form.tsx"
    notifications = "web/components/demo-notifications.tsx"
    dflags = ("web.dashboard",)
    sflags = (*dflags, "web.session_controls")
    pflags = ("web.teacher_login", "web.teacher_profile")
    configured = bool(
        env.get("NEXT_PUBLIC_SUPABASE_URL") and env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    )

    def add(name, route, path, anchor, gates=(), condition="", mounts=(), needs_client=True):
        text = source(root, path)
        found = anchor in text
        evidence = [f"{path}:{text[: text.index(anchor)].count(chr(10)) + 1}"] if found else []
        missing_mounts = []
        for file, token in mounts:
            body = source(root, file)
            if token not in body:
                missing_mounts.append(f"{file} lacks {token}")
            else:
                evidence.append(f"{file}:{body[: body.index(token)].count(chr(10)) + 1}")
        blocked = [
            f"{g}={flags.get(g, {}).get('effective')} "
            f"({flags.get(g, {}).get('source', 'missing registry entry')})"
            for g in gates
            if flags.get(g, {}).get("effective") is not True
        ]
        if not found:
            status, reason = "not found", "Expected implementation anchor missing; inspect source."
        elif missing_mounts:
            status, reason = "unmounted/changed", "; ".join(missing_mounts)
        elif blocked:
            status, reason = "hidden by flag", "; ".join(blocked)
        elif needs_client and not configured:
            status, reason = "blocked by config", "Browser Supabase URL/publishable key missing."
        else:
            status, reason = (
                "reachable; conditional" if condition else "mounted (static)",
                condition,
            )
        features.append(
            dict(
                feature=name,
                code=found,
                route=route,
                component=path,
                gates=list(gates),
                status=status,
                reason=reason,
                evidence=evidence,
            )
        )

    dm = (("web/app/dashboard/page.tsx", "<Dashboard"),)
    sm = (*dm, (dashboard, "<SessionControls"))
    pm = (("web/app/settings/profile/page.tsx", "<TeacherProfileForm"),)
    nm = (*pm, (profile, "<DemoNotifications"))
    detail = "Open a person in the Class list; "
    add(
        "Live camera / MJPEG",
        "/dashboard",
        "web/components/local-classroom-feed.tsx",
        "http://127.0.0.1:8000/stream",
        dflags,
        "Click Turn on video; loopback hostname + running local vision required.",
        (*dm, (dashboard, "<LocalClassroomFeed")),
        needs_client=False,
    )
    add(
        "People / seat cards",
        "/dashboard",
        dashboard,
        "inView.map",
        dflags,
        "Observation rows required; freshness/tracking filters apply "
        "when web.person_observations is on.",
        dm,
    )
    add(
        "Tracking status",
        "/dashboard",
        dashboard,
        "Tracking valid",
        dflags,
        detail + "raw tracking field shown in details; freshness presentation "
        "gated by web.person_observations.",
        dm,
    )
    add(
        "Task score / status",
        "/dashboard",
        dashboard,
        "Match score",
        dflags,
        detail + "score may be unavailable; status remains vision-supplied.",
        dm,
    )
    add(
        "Expression context",
        "/dashboard",
        dashboard,
        "Supporting expression context",
        dflags,
        detail + "only when structured expression_context exists; supporting-only.",
        dm,
    )
    add(
        "Current activity",
        "/dashboard",
        dashboard,
        "{activity}",
        dflags,
        "Session label requires connected session controls; otherwise observation-derived label.",
        dm,
    )
    add(
        "Activity picker",
        "/dashboard",
        controls,
        "snapshot?.activities.map",
        sflags,
        "Authenticated + resolved default station + station membership; "
        "options from read_station_session RPC.",
        sm,
    )
    for name, anchor, condition in (
        ("Start Session", "Starting…", "no active session; activity selected"),
        ("End Session", "Ending…", "active session"),
        (
            "Refresh Session",
            "Refresh activity",
            "enabled unless busy; recovers fetch/action errors",
        ),
        ("Session status", "Session status", "successful session snapshot; expand details"),
    ):
        add(
            name,
            "/dashboard",
            controls,
            anchor,
            sflags,
            "Authenticated + station configured/authorized; " + condition + ".",
            sm,
        )
    add(
        "Pending review queue",
        "/dashboard",
        dashboard,
        "Attention",
        (*dflags, "web.teacher_reviews"),
        "Authenticated owner of session; pending teacher_reviews rows (RLS).",
        dm,
    )
    add(
        "Review details",
        "/dashboard",
        "web/components/person-panel.tsx",
        "Why did Cues ask?",
        (*dflags, "web.teacher_reviews"),
        "Open a person with an owned pending review.",
        (*dm, (dashboard, "<PersonDetails")),
    )
    for name, anchor in (
        ("Support needed", "resolutionLabels.confirmed"),
        ("No support needed", "resolutionLabels.dismissed"),
    ):
        add(
            name,
            "/dashboard",
            "web/components/teacher-review-actions.tsx",
            anchor,
            (*dflags, "web.teacher_reviews", "web.teacher_review_actions"),
            "Open owned pending review; authenticated; "
            "actions disabled while saving or feed unavailable.",
            (*dm, (dashboard, "<TeacherReviewActions")),
        )
    for name, route, gate, anchor in (
        ("Login", "/login", "web.teacher_login", "TeacherLogin"),
        ("Signup", "/signup", "web.teacher_signup", "TeacherLogin"),
    ):
        add(
            name,
            route,
            f"web/app{route}/page.tsx",
            anchor,
            (gate,),
            "Linked from account/sign-in flow; auth form requires browser Supabase config.",
        )
    add(
        "Logout",
        "/settings/profile",
        "web/components/profile-account.tsx",
        "client.auth.signOut()",
        pflags,
        "Authenticated; Sign out sits in the account card on Profile.",
        pm,
    )
    add(
        "Teacher profile",
        "/settings/profile",
        profile,
        "Saving…",
        pflags,
        "Sidebar Teacher profile link; authenticated user.",
        pm,
    )
    add(
        "Phone number",
        "/settings/profile",
        profile,
        'id="profile-phone"',
        pflags,
        "Authenticated; existing profile owns saved phone.",
        pm,
    )
    for name, anchor, condition in (
        (
            "Notification opt-in",
            "I want to receive Cues demo notifications",
            "Saved phone + explicit consent + names.",
        ),
        (
            "Notification activation status",
            "Notifications: ${state}",
            "Own settings; phone must still match consent snapshot.",
        ),
        (
            "Send test notification",
            "Send test notification",
            "Opted in + saved/current/consented phone match; not busy or editing phone.",
        ),
    ):
        add(
            name,
            "/settings/profile",
            notifications,
            anchor,
            pflags,
            "Authenticated; " + condition,
            nm,
        )
    catalog = json.loads(source(root, "vision/activities.json"))
    selector = "snapshot?.activities.map" in source(root, controls)
    notes = []
    for title, activity_id in (
        ("Raise hand activity", "raise_hand"),
        ("Thumbs up activity", "thumbs_up"),
        ("Custom gesture activity", "custom_gesture_01"),
    ):
        item = next((item for item in catalog if item["id"] == activity_id), None)
        add(
            title,
            "/dashboard",
            controls,
            "snapshot?.activities.map",
            sflags,
            "RPC catalog + station_runtime.supported_activity_ids determine options; "
            "hosted contents unknown.",
            sm,
        )
        row = features[-1]
        row["code"] = bool(item and selector)
        row["activity_id"] = activity_id
        row["status"] = (
            "data-dependent" if row["status"] == "reachable; conditional" else row["status"]
        )
        row["evidence"].extend(
            [
                "vision/activities.json",
                "web/lib/session-controls.ts",
                "supabase/migrations/20261114000520_station_session_sync.sql",
            ]
        )
        if activity_id.startswith("custom"):
            row["reason"] += (
                " Built-in placeholder definition; no evidence that templates are recorded."
            )
    sources = []
    for directory, dirs, files in os.walk(root / "web"):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".git", "tests")]
        sources.extend(Path(directory, f).read_text() for f in files if f.endswith((".tsx", ".ts")))
    web_text = "\n".join(sources)
    creation = bool(re.search(r"""["'](?:http[^"']*)?/gestures["']""", web_text))
    features.append(
        dict(
            feature="Custom gesture creation/recording UI",
            code=creation,
            route="none discovered",
            component="vision/routes/gestures.py (backend only)",
            gates=["vision.custom_gestures"],
            status="not implemented in frontend" if not creation else "inspect",
            reason="Vision CRUD + /templates/record exist; no frontend caller found. "
            "Landing page advertises recording.",
            evidence=[
                "vision/routes/gestures.py",
                "vision/routes/templates.py",
                "web/components/landing.tsx",
            ],
        )
    )
    if not creation:
        notes.append(
            "Landing says record your own gesture, but no frontend /gestures caller was found. "
            "vision.custom_gestures controls the local backend API, not a web recording form."
        )
    notes.append(
        "No frontend activity-options array: read_station_session supplies public.activities "
        "filtered by station capabilities. Repo seed only provisions raise_hand; "
        "vision catalog presence does not prove a hosted picker option exists."
    )
    routes = []
    for page in sorted((root / "web/app").rglob("page.tsx")):
        route = "/" + str(page.parent.relative_to(root / "web/app"))
        route = "/" if route == "/." else route
        literals = re.findall(r"""href=["']([^"']+)["']""", web_text)
        linked = any(link.split("#")[0] == route for link in literals)
        routes.append(
            {
                "route": route,
                "source": str(page.relative_to(root)),
                "literal_link_found": linked,
                "note": "literal link found (may be gated)"
                if linked
                else "no literal link; may use dynamic navigation, redirect, or direct URL",
            }
        )
    examples = dotenv_values(root / "web/.env.example", interpolate=False)
    differences = [
        dict(flag=n, **f)
        for n, f in flags.items()
        if f["source"] != "flags.json" or n.startswith("web.") or n == "vision.custom_gestures"
    ]
    example_notes = []
    for n, f in flags.items():
        key = "CUES_FLAG_" + n.upper().replace(".", "_")
        if key in examples and examples[key] in ("0", "1"):
            if (examples[key] == "1") != f["effective"]:
                example_notes.append(
                    f"{key}: example={examples[key]}, effective={f['effective']} "
                    f"from {f['source']}; example is NOT loaded."
                )
    return {
        "scope": "static Cues inventory; reachable != browser-rendered or authorized",
        "launch": "direct Next"
        if direct_next
        else "scripts/dev.sh or demo.sh (inherits root .env)",
        "features": features,
        "flags": differences,
        "routes": routes,
        "notes": notes,
        "example_differences": example_notes,
        "browser_supabase_configured": configured,
    }


def hosted_catalog(root):
    """Optional read-only catalog evidence; do not authenticate as a teacher."""
    from supabase import create_client

    config = {}
    for name in ("web/.env", "web/.env.local", ".env"):
        config.update({k: v for k, v in dotenv_values(root / name).items() if v})
    config.update({k: v for k, v in os.environ.items() if v})
    try:
        client = create_client(config["SUPABASE_URL"], config["SUPABASE_SERVICE_ROLE_KEY"])
        rows = client.table("activities").select("id").execute().data
        station = config.get("CUES_STATION_ID", "S1")
        runtime = (
            client.table("station_runtime")
            .select("supported_activity_ids")
            .eq("station_id", station)
            .execute()
            .data
        )
        return {
            "activity_ids": sorted(row["id"] for row in rows),
            "supported_ids": runtime[0]["supported_activity_ids"] if runtime else None,
            "station_runtime_present": bool(runtime),
        }
    except Exception:
        return {"error": "Hosted catalog unavailable (credentials, connectivity, or schema)."}


def apply_catalog(data, catalog):
    data["hosted_catalog"] = catalog
    if "activity_ids" not in catalog:
        return
    for feature in data["features"]:
        activity = feature.get("activity_id")
        if not activity:
            continue
        missing = activity not in catalog["activity_ids"]
        unsupported = catalog["station_runtime_present"] and activity not in (
            catalog["supported_ids"] or []
        )
        available = not missing and not unsupported
        if available:
            reason = "Present in hosted RPC catalog/capabilities; auth/session still required."
        elif missing:
            reason = f"{activity} absent from hosted public.activities; not a picker option."
        else:
            reason = f"{activity} absent from station supported_activity_ids; not a picker option."
        feature["reason"] = reason + (
            " Custom placeholder is not evidence of recorded templates."
            if activity.startswith("custom")
            else ""
        )
        if feature["status"] == "data-dependent":
            feature["status"] = "catalog option (conditional)" if available else "hidden by catalog"
        if not available:
            data["notes"].append(f"{feature['feature']}: {feature['reason']}")


def runtime_checks(base_url, routes):
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use a loopback HTTP(S) base URL without credentials, query or path.")

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(NoRedirect())
    results = []
    for route in routes:
        try:
            request = Request(base_url.rstrip("/") + route["route"], method="GET")
            with opener.open(request, timeout=10) as response:
                results.append({"route": route["route"], "http": response.status})
        except HTTPError as error:
            results.append({"route": route["route"], "http": error.code})
        except (URLError, TimeoutError, OSError):
            results.append({"route": route["route"], "http": "unavailable"})
    return results


def report(data):
    print(f"UI audit — {data['launch']}")
    print("Static reachability only: auth/session/consent/data and browser DOM are not observed.")
    print("Feature | Code exists | Rendered path / component | Gate | Status")
    print("--- | --- | --- | --- | ---")
    for f in data["features"]:
        print(
            f"{f['feature']} | {'yes' if f['code'] else 'no'} | {f['route']} / "
            f"{Path(f['component']).name} | {', '.join(f['gates']) or 'none'} | {f['status']}"
        )
    print("\nConditions and source evidence")
    for f in data["features"]:
        print(f"- {f['feature']}: {f['reason']} [{'; '.join(f['evidence'])}]")
    print("\nLikely missing from current UI")
    missing = [
        f
        for f in data["features"]
        if f["status"]
        in (
            "hidden by flag",
            "blocked by config",
            "unmounted/changed",
            "placeholder",
            "not implemented in frontend",
            "not found",
            "hidden by catalog",
        )
    ]
    for f in missing:
        print(f"- {f['feature']}: {f['status']} — {f['reason']}")
    for note in data["notes"]:
        print(f"- {note}")
    print("\nEffective flags (default -> effective; winning source)")
    for flag in data["flags"]:
        print(f"- {flag['flag']}: {flag['default']} -> {flag['effective']}; {flag['source']}")
    print("\nTemplate/config differences")
    for note in data["example_differences"]:
        print(f"- {note}")
    print("\nRoutes / navigation")
    for route in data["routes"]:
        print(f"- {route['route']}: {route['note']} [{route['source']}]")
    if "hosted_catalog" in data:
        print("\nHosted catalog (read-only): " + json.dumps(data["hosted_catalog"]))
    if "runtime" in data:
        print(
            "\nRuntime GET checks — HTTP 200 does not prove client hydration, "
            "auth or feature visibility"
        )
        for row in data["runtime"]:
            print(f"- {row['route']}: {row['http']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true", help="GET local page routes; no sign-in")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument(
        "--direct-next", action="store_true", help="Do not inherit launcher root .env"
    )
    parser.add_argument(
        "--hosted-catalog", action="store_true", help="Read activity IDs with backend credentials"
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable report")
    args = parser.parse_args()
    data = audit(direct_next=args.direct_next)
    if args.hosted_catalog:
        apply_catalog(data, hosted_catalog(ROOT))
    if args.runtime:
        try:
            data["runtime"] = runtime_checks(args.base_url, data["routes"])
        except ValueError as error:
            parser.error(str(error))
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        report(data)


if __name__ == "__main__":
    main()
