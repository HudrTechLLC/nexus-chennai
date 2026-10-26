"use client";
import { useState, useTransition } from "react";
import { reviewTip, replyToTip } from "@/app/console/(app)/tips/actions";

export type Nearby = { crime_id: string; station_id: string; fir_no: string; category: string; sub_type: string | null; occurred_from: string; from_appeal: boolean };

/** Mark useful / not useful, optionally linking one of the suggested cases. */
export function ReviewForm({ tipId, nearby }: { tipId: string; nearby: Nearby[] }) {
  const [crime, setCrime] = useState<string>("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();

  const go = (useful: boolean) => start(async () => {
    const r = await reviewTip(tipId, useful, useful && crime ? crime : null, note);
    setMsg(r.ok ? { ok: true, text: useful ? "Marked useful." : "Marked not useful." } : { ok: false, text: r.error });
  });

  return (
    <div className="space-y-3">
      {nearby.length > 0 && (
        <fieldset className="space-y-1 text-sm">
          <legend className="font-semibold">Link to a case (optional)</legend>
          <label className="flex items-center gap-2"><input type="radio" name="crime" checked={crime === ""} onChange={() => setCrime("")} /> None</label>
          {nearby.map((n) => (
            <label key={n.crime_id} className="flex items-center gap-2">
              <input type="radio" name="crime" checked={crime === n.crime_id} onChange={() => setCrime(n.crime_id)} />
              <span className="font-mono text-xs">{n.station_id.replace(/^PS-/, "")} {n.fir_no}</span>
              <span className="text-muted">{n.sub_type?.replaceAll("_", " ") ?? n.category}{n.from_appeal ? " · appeal case" : ""}</span>
            </label>
          ))}
        </fieldset>
      )}
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000} placeholder="Note for other officers (optional)"
        className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm" />
      <div className="flex gap-2">
        <button disabled={pending} onClick={() => go(true)} className="rounded-md bg-signal px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60">Useful</button>
        <button disabled={pending} onClick={() => go(false)} className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-60">Not useful</button>
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </div>
  );
}

/** Reply through the tip code (only when the tipster chose one). */
export function ReplyForm({ tipId, followUp }: { tipId: string; followUp: boolean }) {
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  if (!followUp) return <p className="text-sm text-muted">The tipster chose full anonymity, so there is no way to reply.</p>;
  return (
    <form className="space-y-2" onSubmit={(e) => {
      e.preventDefault();
      start(async () => {
        const r = await replyToTip(tipId, followUp, text);
        if (r.ok) { setText(""); setMsg({ ok: true, text: "Reply sent. The tipster sees it on Check a tip." }); } else setMsg({ ok: false, text: r.error });
      });
    }}>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000}
        placeholder="Reply to the tipster. Never ask for their identity." className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm" />
      <button disabled={pending || !text.trim()} className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-60">{pending ? "Sending…" : "Send reply"}</button>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </form>
  );
}
