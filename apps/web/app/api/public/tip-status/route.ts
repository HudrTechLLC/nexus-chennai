import { clientAddr, publicClient, rateLimited, reply } from "@/lib/publicApi";
import { normaliseTipCode } from "@/lib/tip";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Tip status and tipster replies (spec G1 /tip/status). The code + passphrase are checked inside
 * Postgres (bcrypt, lockout after 5 failures; D-023). The same answer is given for a wrong code and
 * a wrong passphrase. Nothing here is logged.
 */
export async function POST(req: Request) {
  if (await rateLimited(clientAddr(req.headers), "tip-status", 20, 10 * 60_000)) {
    return reply({ ok: false, error: "Too many attempts. Please wait a few minutes." }, 429);
  }
  let body: { code?: string; passphrase?: string; reply?: string };
  try {
    body = await req.json();
  } catch {
    return reply({ ok: false, error: "Bad request." }, 400);
  }
  const code = normaliseTipCode(body.code ?? "");
  const passphrase = typeof body.passphrase === "string" ? body.passphrase.slice(0, 128) : "";
  if (!code || !passphrase) return reply({ ok: false, error: "That code and passphrase do not match a tip." }, 200);

  const sb = publicClient();
  if (typeof body.reply === "string" && body.reply.trim()) {
    const { data, error } = await sb.rpc("tip_reply", { p_code: code, p_passphrase: passphrase, p_text: body.reply.slice(0, 2000) });
    if (error) return reply({ ok: false, error: "Could not send. Please try again." }, 502);
    if (!(data as { ok: boolean }).ok) return reply(mapError(data as { error: string }));
  }
  const { data, error } = await sb.rpc("tip_status", { p_code: code, p_passphrase: passphrase });
  if (error) return reply({ ok: false, error: "Could not check. Please try again." }, 502);
  const d = data as { ok: boolean; error?: string };
  return reply(d.ok ? d : mapError(d as { error: string }));
}

function mapError(d: { error: string }) {
  if (d.error === "locked") return { ok: false, error: "Too many wrong tries for this code. Please wait 15 minutes." };
  if (d.error === "invalid_text") return { ok: false, error: "Write a reply of up to 2000 characters." };
  return { ok: false, error: "That code and passphrase do not match a tip." };
}
