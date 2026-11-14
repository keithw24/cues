import type { SupabaseClient } from "@supabase/supabase-js";

export async function testDemoNotification(request: Request, admin: SupabaseClient,
  send: (userId: string) => Promise<{status?: string; error?: string}>) {
  const reply = (body: object, status = 200) => Response.json(body, {
    status, headers: {"Cache-Control": "no-store"},
  });
  const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/i)?.[1];
  if (!token) return reply({error: "Sign in to test notifications."}, 401);
  try {
    const {data, error} = await admin.auth.getUser(token);
    if (error || !data.user) return reply({error: "Sign in to test notifications."}, 401);
    // No destination or identity input is accepted from the browser.
    if ((await request.text()).trim() !== "") return reply({error: "No test parameters are accepted."}, 400);
    const result = await send(data.user.id);
    if (result.status === "registered") return reply({status: "registered"});
    if (result.status === "pending") return reply({status: "pending"}, 202);
  } catch { /* Only safe application messages leave the server. */ }
  return reply({error: "Notification test failed. Check activation and try again."}, 503);
}
