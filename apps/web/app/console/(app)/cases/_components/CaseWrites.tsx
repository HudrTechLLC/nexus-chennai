"use client";
import { useState, useTransition } from "react";
import { CASE_STATUSES, DIARY_KINDS, DIARY_MAX, humanise } from "@/lib/cases";
import { addDiaryEntry, setCaseStatus } from "../[crimeId]/actions";

const input = "rounded-md border border-line bg-bg px-2 py-1.5 text-sm";

function Msg({ msg }: { msg: { ok: boolean; text: string } | null }) {
  return msg ? <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p> : null;
}

/** Add a dated case diary entry (spec CAP-04). */
export function DiaryForm({ crimeId }: { crimeId: string }) {
  const [kind, setKind] = useState<string>("lead");
  const [text, setText] = useState("");
  const [at, setAt] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  return (
    <form
      className="space-y-2 rounded-lg border border-dashed border-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await addDiaryEntry(crimeId, { kind, text, at });
          setMsg(r.ok ? { ok: true, text: "Entry added." } : { ok: false, text: r.error });
          if (r.ok) { setText(""); setAt(""); }
        });
      }}
    >
      <div className="flex flex-wrap gap-2">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={input} aria-label="Entry type">
          {DIARY_KINDS.map((k) => <option key={k} value={k}>{humanise(k)}</option>)}
        </select>
        <label className="flex items-center gap-1 text-xs text-muted">when (blank = now)
          <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} className={input} />
        </label>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={DIARY_MAX} rows={3} className={`${input} w-full`} placeholder="What was done or learned" aria-label="Diary entry" />
      <div className="flex items-center gap-3">
        <button disabled={pending || !text.trim()} className="rounded-md bg-ink px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-50">{pending ? "Saving…" : "Add diary entry"}</button>
        <Msg msg={msg} />
      </div>
    </form>
  );
}

/** Change the case status (spec CAP-01); every change is audited. */
export function StatusForm({ crimeId, status }: { crimeId: string; status: string }) {
  const [to, setTo] = useState(status);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <select value={to} onChange={(e) => setTo(e.target.value)} className={input} aria-label="Case status">
        {CASE_STATUSES.map((s) => <option key={s} value={s} disabled={s === "registered" && status !== "registered"}>{humanise(s)}</option>)}
      </select>
      <button
        type="button"
        disabled={pending || to === status}
        onClick={() => start(async () => {
          const r = await setCaseStatus(crimeId, to);
          setMsg(r.ok ? { ok: true, text: "Status updated." } : { ok: false, text: r.error });
        })}
        className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-bg disabled:opacity-50"
      >
        {pending ? "Saving…" : "Set status"}
      </button>
      <Msg msg={msg} />
    </span>
  );
}
