import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";

// Resolve relative to this sender, regardless of the Python caller's cwd.
loadEnvFile(fileURLToPath(new URL("../.env", import.meta.url)));
const diagnostic = console.error.bind(console);
// SDK logging can contain addresses; only emit our sanitized diagnostics.
console.log = console.info = console.warn = console.debug = console.error = () => {};
function safe(message: string) {
  for (const name of ["SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET",
    "SPECTRUM_TEACHER_PHONE", "SPECTRUM_SENDER_PHONE"]) {
    const value = process.env[name];
    if (value) message = message.split(value).join("[redacted]");
  }
  return message.replace(/\+\d[\d ()-]{6,}\d/g, "[phone]")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]");
}

let stage = "input";
async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  const { message } = JSON.parse(input);
  if (typeof message !== "string" || message.length > 500) throw new Error("Invalid message");
  const phone = process.env.SPECTRUM_TEACHER_PHONE;
  if (!phone) throw new Error("Teacher destination missing");
  if (!process.env.SPECTRUM_PROJECT_ID || !process.env.SPECTRUM_PROJECT_SECRET)
    throw new Error("Spectrum project credentials missing");
  diagnostic(JSON.stringify({ cuesNotification: true, config: {
    nestedEnvLoaded: true, projectIdPresent: true, projectSecretPresent: true,
    teacherPresent: true, explicitSender: Boolean(process.env.SPECTRUM_SENDER_PHONE),
  }}));
  stage = "connect";
  const app = await Spectrum({
    projectId: process.env.SPECTRUM_PROJECT_ID!,
    projectSecret: process.env.SPECTRUM_PROJECT_SECRET!,
    providers: [imessage.config()],
  });
  try {
    const provider = imessage(app);
    stage = "resolve-teacher";
    const user = await provider.user(phone);
    stage = "resolve-space";
    const space = await provider.space.create(user, process.env.SPECTRUM_SENDER_PHONE
      ? { phone: process.env.SPECTRUM_SENDER_PHONE } : undefined);
    stage = "send";
    const sent = await space.send(message);
    if (!sent || (Array.isArray(sent) && sent.length === 0)) throw new Error("No acknowledgement");
  } finally { await app.stop(); }
  process.stdout.write(JSON.stringify({ accepted: true }) + "\n");
}
main().catch((error) => {
  diagnostic(JSON.stringify({ cuesNotification: true, stage,
    error: safe(error instanceof Error ? error.message : String(error)) }));
  process.exitCode = 1;
});
