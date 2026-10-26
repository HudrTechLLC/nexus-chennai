"use client";
import { useState, useTransition } from "react";
import Link from "next/link";
import { requestDraft } from "@/app/console/(app)/appeals/actions";

/** Case file → "publish public appeal" (G2): asks the Sanitiser for a draft; the officer edits and publishes in Appeals. */
export function AppealButton({ crimeId }: { crimeId: string }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={pending || msg?.ok}
        onClick={() => start(async () => {
          const r = await requestDraft(crimeId);
          setMsg(r.ok ? { ok: true, text: "Draft requested." } : { ok: false, text: r.error });
        })}
        className="rounded-md border border-line px-3 py-1.5 hover:bg-bg disabled:opacity-60"
      >
        {pending ? "Requesting…" : "Draft public appeal"}
      </button>
      {msg && (
        <span role={msg.ok ? "status" : "alert"} className={`text-xs ${msg.ok ? "text-signal" : "text-red-600"}`}>
          {msg.text} {msg.ok && <Link href="/console/appeals" className="underline">Open Appeals</Link>}
        </span>
      )}
    </span>
  );
}
