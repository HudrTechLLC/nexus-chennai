"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { leakKind, parseLookingFor, validateAppeal, type Appeal } from "@/lib/appeals";
import { requestDraft, saveAppeal } from "@/app/console/(app)/appeals/actions";

/** Ask the Sanitiser (via the worker) for a draft public appeal for one case. */
export function RequestDraftForm() {
  const [crimeId, setCrimeId] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await requestDraft(crimeId);
          setMsg(r.ok ? { ok: true, text: "Requested. The draft appears below within a minute." } : { ok: false, text: r.error });
          if (r.ok) { setCrimeId(""); router.refresh(); }
        });
      }}
    >
      <label className="text-sm">
        <span className="mb-1 block text-muted">Case id</span>
        <input value={crimeId} onChange={(e) => setCrimeId(e.target.value)} placeholder="CHN-AD-2026-001182"
               className="w-64 rounded-md border border-line bg-bg px-2 py-1.5 font-mono text-sm" />
      </label>
      <button disabled={pending || !crimeId.trim()} className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
        Request draft appeal
      </button>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`w-full text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </form>
  );
}

/** Edit a draft and publish it, or withdraw a published appeal. The database re-checks every published word. */
export function AppealEditor({ appeal, canWrite }: { appeal: Appeal; canWrite: boolean }) {
  const [title, setTitle] = useState(appeal.title);
  const [area, setArea] = useState(appeal.area_label);
  const [summary, setSummary] = useState(appeal.summary);
  const [lookingFor, setLookingFor] = useState(appeal.looking_for.join("\n"));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();
  const edit = { title, area_label: area, summary, looking_for: parseLookingFor(lookingFor) };
  const live = validateAppeal(edit);
  const readOnly = !canWrite || appeal.status === "withdrawn";

  function run(action: "save" | "publish" | "withdraw") {
    start(async () => {
      const r = await saveAppeal(appeal.public_incident_id, { title, area_label: area, summary, looking_for: lookingFor, action });
      const done = { save: "Saved.", publish: "Published. It appears on the public appeals page within a minute.", withdraw: "Withdrawn from the public site." };
      setMsg(r.ok ? { ok: true, text: done[action] } : { ok: false, text: r.error });
      if (r.ok) router.refresh();
    });
  }

  const field = "w-full rounded-md border border-line bg-bg px-2 py-1.5 text-sm";
  return (
    <div className="space-y-3">
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Title</span>
        <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} disabled={readOnly} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Area shown to the public (a locality or road, never a landmark or door number)</span>
        <input className={field} value={area} onChange={(e) => setArea(e.target.value)} disabled={readOnly} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Summary</span>
        <textarea className={field} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} disabled={readOnly} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Looking for (one per line, up to 4)</span>
        <textarea className={field} rows={4} value={lookingFor} onChange={(e) => setLookingFor(e.target.value)} disabled={readOnly} />
      </label>
      {!readOnly && live && <p role="alert" className="text-sm text-red-600">{live}</p>}
      {!readOnly && !live && leakKind(`${title} ${area} ${summary} ${lookingFor}`) === null && (
        <p className="text-xs text-muted">No plates, phone numbers, case or FIR numbers found. The database checks again when you publish.</p>
      )}
      {canWrite && (
        <div className="flex flex-wrap gap-2">
          {appeal.status !== "withdrawn" && (
            <button disabled={pending || !!live} onClick={() => run("save")} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-bg disabled:opacity-60">
              Save
            </button>
          )}
          {appeal.status === "draft" && (
            <button disabled={pending || !!live} onClick={() => run("publish")} className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
              Approve and publish
            </button>
          )}
          {appeal.status === "published" && (
            <button disabled={pending} onClick={() => run("withdraw")} className="rounded-md border border-red-500 px-3 py-2 text-sm text-red-600 disabled:opacity-60">
              Withdraw
            </button>
          )}
        </div>
      )}
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </div>
  );
}
