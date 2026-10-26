"use client";
import { useState, useTransition } from "react";
import { humanise, MO_FIELDS, moToText, type MoField } from "@/lib/cases";
import { reviewMo } from "../[crimeId]/actions";

const input = "w-full rounded-md border border-line bg-bg px-2 py-1 text-sm";

/** Lets the case's station correct or confirm the Extractor's MO. Corrections are stored separately. */
export function MoReview({ crimeId, mo }: { crimeId: string; mo: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const [edited, setEdited] = useState<Partial<Record<MoField, string>>>({});
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();

  if (!open) {
    return (
      <div className="space-y-1">
        <button type="button" onClick={() => { setOpen(true); setMsg(null); }} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-bg">
          Review or correct the MO
        </button>
        {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
      </div>
    );
  }
  return (
    <form
      className="space-y-2 rounded-lg border border-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await reviewMo(crimeId, edited, note);
          if (r.ok) {
            setMsg({ ok: true, text: r.changed ? `Saved ${r.changed} correction${r.changed === 1 ? "" : "s"}.` : "Marked as reviewed: no changes." });
            setOpen(false);
            setEdited({});
            setNote("");
          } else setMsg({ ok: false, text: r.error });
        });
      }}
    >
      <p className="text-xs text-muted">Change only what is wrong. Lists are comma-separated. The Extractor&apos;s original stays on record.</p>
      <dl className="grid grid-cols-[7.5rem_1fr] items-center gap-x-2 gap-y-1 text-sm">
        {MO_FIELDS.map((f) => (
          <div key={f} className="contents">
            <dt className="text-muted">{humanise(f)}</dt>
            <dd>
              <input
                value={edited[f] ?? moToText(mo[f])}
                onChange={(e) => setEdited((p) => ({ ...p, [f]: e.target.value }))}
                inputMode={f === "offender_count" ? "numeric" : undefined}
                className={input}
                aria-label={humanise(f)}
              />
            </dd>
          </div>
        ))}
      </dl>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2} placeholder="Why (optional)" className={input} />
      <div className="flex flex-wrap items-center gap-2">
        <button disabled={pending} className="rounded-md bg-ink px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-60">{pending ? "Saving…" : "Save review"}</button>
        <button type="button" onClick={() => { setOpen(false); setEdited({}); }} className="text-sm text-muted hover:text-ink">Cancel</button>
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </form>
  );
}
