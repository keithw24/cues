import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";
import { sendSpectrumMessage, SpectrumSendError } from "./send.ts";

loadEnvFile(fileURLToPath(new URL("../.env", import.meta.url)));
async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  const {message, destination} = JSON.parse(input);
  const phone = process.env.CUES_USE_STATIC_TEACHER_PHONE === "1"
    ? process.env.SPECTRUM_TEACHER_PHONE : destination;
  await sendSpectrumMessage({projectId: process.env.SPECTRUM_PROJECT_ID ?? "",
    projectSecret: process.env.SPECTRUM_PROJECT_SECRET ?? "",
    senderPhone: process.env.SPECTRUM_SENDER_PHONE}, phone, message);
  process.stdout.write(JSON.stringify({accepted: true}) + "\n");
}
main().catch(error => {
  const category = error instanceof SpectrumSendError ? error.category : "provider_failure";
  console.error(JSON.stringify({cuesNotification: true, category}));
  process.stdout.write(JSON.stringify({accepted: false, category}) + "\n");
  process.exitCode = 1;
});
