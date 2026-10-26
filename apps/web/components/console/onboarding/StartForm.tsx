"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { validateStart } from "@/lib/onboarding";

const input = "w-full rounded-md border border-line bg-bg px-3 py-2 text-sm";

/** Start onboarding a new source (WS1-23): a key, a label, and an uploaded CSV or the bundled sample export. */
export function StartForm() {
  const router = useRouter();
  const [sourceKey, setSourceKey] = useState("");
  const [label, setLabel] = useState("");
  const [useSample, setUseSample] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setExisting(null);
    const f = validateStart({ sourceKey, label, useSample, file: file ? { name: file.name, size: file.size } : null });
    setFields(f);
    if (Object.keys(f).length) return;
    const body = new FormData();
    body.set("source_key", sourceKey);
    body.set("label", label);
    body.set("use_sample", String(useSample));
    if (!useSample && file) body.set("file", file);
    setBusy(true);
    try {
      const res = await fetch("/console/system/sources/onboard/start", { method: "POST", body });
      const out = await res.json().catch(() => ({ ok: false, error: `HTTP ${res.status}` }));
      if (out.ok) {
        router.push(`/console/system/sources/onboard/${encodeURIComponent(out.runId)}`);
        return;
      }
      setFields(out.fields ?? {});
      setError(out.error ?? "Could not start.");
      if (out.runId) setExisting(out.runId);
    } catch {
      setError("Network error. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const err = (k: string) => fields[k] && <p className="mt-1 text-xs text-red-600">{fields[k]}</p>;

  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-5" noValidate>
      <h2 className="font-semibold">Start a run</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label htmlFor="ob-key" className="text-sm font-medium">Source key</label>
          <input id="ob-key" className={input} value={sourceKey} maxLength={30} placeholder="e.g. redhills_new"
            onChange={(e) => setSourceKey(e.target.value.toLowerCase())} aria-invalid={!!fields.source_key} aria-describedby="ob-key-help" />
          <p id="ob-key-help" className="mt-1 text-xs text-muted">Becomes the Zetaris view name onboard_&lt;key&gt;. Lower-case letters, digits, _.</p>
          {err("source_key")}
        </div>
        <div>
          <label htmlFor="ob-label" className="text-sm font-medium">Name</label>
          <input id="ob-label" className={input} value={label} maxLength={80} placeholder="e.g. Red Hills (new station) register"
            onChange={(e) => setLabel(e.target.value)} aria-invalid={!!fields.label} />
          {err("label")}
        </div>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Export</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="ob-src" checked={useSample} onChange={() => setUseSample(true)} />
          Use the sample export (a synthetic new station&apos;s register, bundled with Nexus)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="radio" name="ob-src" checked={!useSample} onChange={() => setUseSample(false)} />
          Upload a CSV export (up to 2 MB)
        </label>
        {!useSample && (
          <div>
            <label htmlFor="ob-file" className="sr-only">CSV export</label>
            <input id="ob-file" type="file" accept=".csv,text/csv" className="text-sm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-invalid={!!fields.file} />
            {err("file")}
          </div>
        )}
      </fieldset>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}{" "}
          {existing && <Link className="underline" href={`/console/system/sources/onboard/${encodeURIComponent(existing)}`}>Open it</Link>}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
          {busy ? "Starting…" : "Start onboarding"}
        </button>
        <p className="text-xs text-muted">The worker profiles it through Zetaris and proposes a mapping. Nothing is linked until reviewed.</p>
      </div>
    </form>
  );
}

export default StartForm;
