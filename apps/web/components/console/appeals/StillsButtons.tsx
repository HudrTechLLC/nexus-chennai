"use client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { attachStill, detachStill } from "@/app/console/(app)/appeals/[id]/stills-actions";

export function AttachButton({ appealId, evidenceId, disabled }: { appealId: string; evidenceId: string; disabled?: boolean }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <div>
      <button type="button" disabled={pending || disabled} className="rounded-md bg-signal px-2 py-1 text-xs font-medium text-white disabled:opacity-60"
        onClick={() => start(async () => {
          const r = await attachStill(appealId, evidenceId);
          if (r.ok) { setError(null); router.refresh(); } else setError(r.error);
        })}>
        {pending ? "Blurring…" : "Attach blurred copy"}
      </button>
      {error && <p role="alert" className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function DetachButton({ appealId, path }: { appealId: string; path: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <div>
      <button type="button" disabled={pending} className="text-xs text-red-600 hover:underline disabled:opacity-60"
        onClick={() => start(async () => {
          const r = await detachStill(appealId, path);
          if (r.ok) { setError(null); router.refresh(); } else setError(r.error);
        })}>
        {pending ? "Removing…" : "Remove from appeal"}
      </button>
      {error && <p role="alert" className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
