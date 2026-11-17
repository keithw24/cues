import "server-only";
import {parseEnv} from "node:util";
import {readFileSync} from "node:fs";
import path from "node:path";

export function notificationServerConfig() {
  const root = path.resolve(process.cwd(), process.cwd().endsWith(path.sep + "web") ? ".." : ".");
  const config: Record<string, string> = {};
  for (const file of [".env"]) {
    try {Object.assign(config, parseEnv(readFileSync(path.join(root, file), "utf8")));}
    catch { /* Hosted deployments use backend environment variables only. */ }
  }
  for (const [key, value] of Object.entries(process.env)) if (value) config[key] = value;
  return config;
}
