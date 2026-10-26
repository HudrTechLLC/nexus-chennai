"use client";

import { useEffect, useState, type ReactNode } from "react";
import { readDismissed, writeDismissed } from "@/lib/startHere";

/**
 * Wraps the server-rendered Start-here strip so each user can hide it. Shown on the server and on the first
 * client render (no hydration mismatch); a stored dismissal is read after mount. Storage failures mean shown.
 */
export function DismissibleStrip({ storageKey, children }: { storageKey: string; children: ReactNode }) {
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.localStorage;
    } catch {
      storage = null;
    }
    setDismissed(readDismissed(storage, storageKey));
  }, [storageKey]);

  if (dismissed) return null;

  const dismiss = () => {
    try {
      writeDismissed(window.localStorage, storageKey, true);
    } catch {
      /* no storage: hide for this visit only */
    }
    setDismissed(true);
  };

  return (
    <div className="flex items-start gap-3 rounded-xl border border-[color-mix(in_srgb,var(--signal)_45%,transparent)] bg-surface px-4 py-3 shadow-card">
      <div className="min-w-0 flex-1">{children}</div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Hide Start here"
        title="Hide Start here"
        className="shrink-0 rounded-md px-1.5 text-lg leading-none text-muted hover:bg-surface-2 hover:text-ink"
      >
        ×
      </button>
    </div>
  );
}

export default DismissibleStrip;
