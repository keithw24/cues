import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";

export type SendCategory = "target_not_allowed" | "provider_failure" | "network_failure";
export class SpectrumSendError extends Error {
  constructor(public readonly category: SendCategory) { super(category); }
}
export type SpectrumSendConfig = {
  projectId: string; projectSecret: string; senderPhone?: string;
};
type Session = {send: (phone: string, message: string) => Promise<unknown>; stop: () => Promise<void>};
type Connect = (config: SpectrumSendConfig, signal: AbortSignal) => Promise<Session>;
const connect: Connect = async (config, signal) => {
  const app = await Spectrum({projectId: config.projectId, projectSecret: config.projectSecret,
    providers: [imessage.config()], signal, telemetry: false, options: {logLevel: "silent"}});
  return {
    async send(phone, message) {
      const provider = imessage(app);
      const user = await provider.user(phone);
      const space = await provider.space.create(user,
        config.senderPhone ? {phone: config.senderPhone} : undefined);
      return space.send(message);
    },
    stop: () => app.stop(),
  };
};

/** Server/CLI only. One bounded send, no automatic retry or destination fallback. */
export async function sendSpectrumMessage(config: SpectrumSendConfig, phone: string,
  message: string, factory: Connect = connect, timeoutMs = 20000): Promise<void> {
  if (!config.projectId || !config.projectSecret || !/^\+[1-9]\d{7,14}$/.test(phone) ||
      !message || message.length > 500) throw new SpectrumSendError("provider_failure");
  const controller = new AbortController();
  let session: Session | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {controller.abort(); reject(new SpectrumSendError("network_failure"));}, timeoutMs);
    });
    const work = (async () => {
      session = await factory(config, controller.signal);
      if (controller.signal.aborted) {await session.stop(); throw new SpectrumSendError("network_failure");}
      const sent = await session.send(phone, message);
      const messages = Array.isArray(sent) ? sent : [sent];
      // iMessage acknowledgements expose isSent. A resolved call or empty result is insufficient.
      if (!messages.length || messages.some(m => !m || typeof m !== "object" || m.isSent !== true))
        throw new SpectrumSendError("provider_failure");
    })();
    await Promise.race([work, deadline]);
  } catch (error) {
    if (error instanceof SpectrumSendError) throw error;
    const denied = error instanceof Error && error.message.includes("Target not allowed for this project");
    throw new SpectrumSendError(denied ? "target_not_allowed" : "provider_failure");
  } finally {
    if (timer) clearTimeout(timer);
    controller.abort();
    if (session) {
      let cleanup: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([session.stop(), new Promise<void>(resolve => {
          cleanup = setTimeout(resolve, 2000);
        })]);
      } catch { /* Delivery outcome remains authoritative; never log provider payloads. */ }
      finally {if (cleanup) clearTimeout(cleanup);}
    }
  }
}
