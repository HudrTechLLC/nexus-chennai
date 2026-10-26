"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { formatTipCode } from "@/lib/tip";

/** Confirmation (spec G1 /tip/sent): the tip code is shown once, then forgotten by this page. */
export function TipSent() {
  const [info, setInfo] = useState<{ code: string | null; week: string } | null | undefined>(undefined);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("nexus-tip-sent");
      sessionStorage.removeItem("nexus-tip-sent");
      setInfo(raw ? JSON.parse(raw) : null);
    } catch {
      setInfo(null);
    }
  }, []);

  if (info === undefined) return null;
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-3xl font-bold">Thank you. Your tip was sent.</h1>
      {info?.code ? (
        <section className="rounded-xl border border-signal bg-surface p-5">
          <p className="text-sm">Your tip code. It is shown <strong>only once</strong>:</p>
          <p className="mt-2 font-mono text-4xl tracking-widest">{formatTipCode(info.code)}</p>
          <button
            className="mt-3 rounded-md border border-line px-3 py-1.5 text-sm"
            onClick={() => { void navigator.clipboard.writeText(formatTipCode(info.code!)); setCopied(true); }}
          >
            {copied ? "Copied" : "Copy code"}
          </button>
          <p className="mt-3 text-sm text-muted">With this code and your passphrase you can read police replies at <Link className="underline" href="/tip/status">Check a tip</Link>. Neither can be recovered.</p>
        </section>
      ) : info === null ? (
        <p className="text-muted">This page shows a tip code only right after sending. If you chose a code, you saw it then.</p>
      ) : (
        <p className="text-muted">You chose to stay fully anonymous, so there is no way for police to reply.</p>
      )}
      <section className="rounded-xl border border-line bg-surface p-5 text-sm">
        <h2 className="font-semibold">What happens next</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
          <li>An automatic screen checks the tip for spam and unsafe content.</li>
          <li>Station officers and analysts read it alongside the cases it may relate to.</li>
          <li>If you chose a tip code, any reply appears on the Check a tip page.</li>
        </ol>
      </section>
      <Link href="/" className="inline-block text-sm underline">Back to home</Link>
    </div>
  );
}
