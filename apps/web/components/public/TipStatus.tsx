"use client";
import { useState } from "react";

type Status = { ok: true; tip_id: string; status: string; received_week: string; messages: { sender: "police" | "tipster"; text: string; on: string }[] };

const STATUS_LABEL: Record<string, string> = { received: "Received", reviewed: "Reviewed by police", closed: "Closed" };

/** Tip status timeline and reply box (spec G1 /tip/status). The passphrase stays in memory only. */
export function TipStatus() {
  const [code, setCode] = useState("");
  const [pass, setPass] = useState("");
  const [data, setData] = useState<Status | null>(null);
  const [replyText, setReplyText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(extra: { reply?: string } = {}) {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/public/tip-status", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit", referrerPolicy: "no-referrer",
        body: JSON.stringify({ code, passphrase: pass, ...extra }),
      });
      const j = await r.json();
      if (j.ok) { setData(j); if (extra.reply) setReplyText(""); } else { setData(null); setError(j.error); }
    } catch {
      setError("Network problem. Please try again.");
    }
    setBusy(false);
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); void call(); }} className="space-y-3 rounded-xl border border-line bg-surface p-5">
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Tip code, e.g. 8F3K·2QWA" autoComplete="off" spellCheck={false}
          className="w-full rounded-md border border-line bg-bg px-3 py-2 font-mono uppercase tracking-widest" />
        <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Passphrase" autoComplete="current-password"
          className="w-full rounded-md border border-line bg-bg px-3 py-2" />
        <button disabled={busy} className="rounded-md bg-signal px-4 py-2 font-medium text-white disabled:opacity-60">{busy ? "Checking…" : "Check"}</button>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      </form>

      {data && (
        <section className="space-y-4 rounded-xl border border-line bg-surface p-5">
          <p className="text-sm">Status: <strong>{STATUS_LABEL[data.status] ?? data.status}</strong> · sent in week {data.received_week}</p>
          <ol className="space-y-2">
            {data.messages.length === 0 && <li className="text-sm text-muted">No messages yet.</li>}
            {data.messages.map((m, i) => (
              <li key={i} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${m.sender === "police" ? "bg-signal-soft" : "ml-auto bg-bg"}`}>
                <p className="text-xs text-muted">{m.sender === "police" ? "Police" : "You"} · {m.on}</p>
                <p className="whitespace-pre-line">{m.text}</p>
              </li>
            ))}
          </ol>
          <form onSubmit={(e) => { e.preventDefault(); if (replyText.trim()) void call({ reply: replyText }); }} className="space-y-2">
            <textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={3} maxLength={2000}
              placeholder="Reply to the police (don't include anything that identifies you)" className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm" />
            <button disabled={busy || !replyText.trim()} className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-60">Send reply</button>
          </form>
        </section>
      )}
    </div>
  );
}
