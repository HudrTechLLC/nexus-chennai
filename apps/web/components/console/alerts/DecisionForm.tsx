"use client";
import { useState, useTransition } from "react";
import { REASON_CODES, REASON_LABEL, validateDecision } from "@/lib/alerts";
import { decideAlert } from "@/app/console/(app)/alerts/[alertId]/actions";

/** Approve / reject with reason (spec G2, F4). Shown only to analyst, supervisor and admin. */
export function DecisionForm({ alertId, stationsLabel }: { alertId: string; stationsLabel: string }) {
  const [mode, setMode] = useState<"idle" | "reject">("idle");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function submit(decision: "approve" | "reject") {
    const input = { decision, reason_code: decision === "reject" ? reason : undefined, note };
    const problem = validateDecision(input);
    if (problem) return setError(problem);
    setError(null);
    start(async () => {
      const r = await decideAlert(alertId, input);
      if (r.ok) setDone(decision === "approve" ? "Approved. Both stations will be notified." : "Rejected. The reason is visible to every station and saved to memory.");
      else setError(r.error);
    });
  }

  if (done) return <p className="rounded-md border border-signal bg-signal-soft px-3 py-2 text-sm">{done}</p>;

  return (
    <div className="space-y-3">
      {mode === "idle" ? (
        <div className="flex flex-wrap gap-2">
          <button disabled={pending} onClick={() => submit("approve")} className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
            Approve and notify {stationsLabel}
          </button>
          <button disabled={pending} onClick={() => setMode("reject")} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-bg">
            Reject with reason
          </button>
        </div>
      ) : (
        <div className="space-y-2 rounded-lg border border-line p-3">
          <fieldset>
            <legend className="text-sm font-semibold">Why is this not a link?</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {REASON_CODES.map((r) => (
                <label key={r} className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${reason === r ? "border-signal bg-signal-soft" : "border-line"}`}>
                  <input type="radio" name="reason" value={r} className="sr-only" checked={reason === r} onChange={() => setReason(r)} />
                  {REASON_LABEL[r]}
                </label>
              ))}
            </div>
          </fieldset>
          <textarea
            value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000}
            placeholder="Note for the other stations (optional unless the reason is Other)"
            className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm"
          />
          <div className="flex gap-2">
            <button disabled={pending} onClick={() => submit("reject")} className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
              {pending ? "Saving…" : "Reject"}
            </button>
            <button disabled={pending} onClick={() => setMode("idle")} className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink">Cancel</button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
