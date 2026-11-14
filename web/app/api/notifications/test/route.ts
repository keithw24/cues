import "server-only";
import { createClient } from "@supabase/supabase-js";
import { spawn } from "node:child_process";
import { parseEnv } from "node:util";
import { readFileSync } from "node:fs";
import path from "node:path";
import { testDemoNotification } from "@/lib/notification-test";

export async function POST(request: Request) {
  const root = path.resolve(process.cwd(), process.cwd().endsWith(path.sep + "web") ? ".." : ".");
  const config: Record<string, string> = {};
  for (const file of [".env", "cues/.env"]) {
    try { Object.assign(config, parseEnv(readFileSync(path.join(root, file), "utf8"))); }
    catch { /* Deployment may use process environment instead. */ }
  }
  for (const [key, value] of Object.entries(process.env)) if (value) config[key] = value;
  if (!config.SUPABASE_URL || !config.SUPABASE_SERVICE_ROLE_KEY)
    return Response.json({error: "Notifications are not configured."}, {status: 503});
  const admin = createClient(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY,
    {auth: {persistSession: false, autoRefreshToken: false}});
  return testDemoNotification(request, admin, userId => new Promise((resolve) => {
    // Reuse the review sender's exact eligibility and atomic acknowledgement path.
    const child = spawn(path.join(root, ".venv/bin/python"), ["-m", "agent.notification_activation"],
      {cwd: root, stdio: ["pipe", "pipe", "pipe"]});
    let output = "";
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve({error: "timeout"}); }, 35000);
    child.stdout.on("data", chunk => { output += chunk; });
    child.stderr.resume(); // Provider diagnostics must not reach browser/log output.
    child.on("error", () => {clearTimeout(timer); resolve({error: "unavailable"});});
    child.on("close", () => {
      clearTimeout(timer);
      try { resolve(JSON.parse(output)); } catch { resolve({error: "unavailable"}); }
    });
    child.stdin.on("error", () => {});
    const names = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SPECTRUM_PROJECT_ID",
      "SPECTRUM_PROJECT_SECRET", "SPECTRUM_SENDER_PHONE"];
    child.stdin.end(JSON.stringify({root, user_id: userId,
      config: Object.fromEntries(names.map(name => [name, config[name]]))}));
  }));
}
