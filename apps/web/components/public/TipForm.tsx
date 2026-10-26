"use client";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { cleanImage, faceDetectionAvailable } from "@/lib/stripImage";
import {
  formatTipCode, generateTipCode, MAX_FILE_BYTES, MAX_FILES, solvePow, TIP_CATEGORIES, TIP_CATEGORY_LABEL,
  validateTip, type TipCategory,
} from "@/lib/tip";
import { TIP_WHEN as WHEN, tipFields, type TipSubject, type TipWhen } from "@/lib/tipPrefill";

const HexPicker = dynamic(() => import("./HexPicker").then((m) => m.HexPicker), {
  ssr: false, loading: () => <div className="h-64 rounded-lg border border-line bg-bg" />,
});

type Item = { name: string; kind: "image" | "audio"; blob: Blob; preview: string | null; facesBlurred: boolean; note: string };

/**
 * Anonymous tip in 3 steps (spec G1 /tip/new; exhibit "Anonymous tip").
 * A `subject` (WS4-12, from ?appeal= or ?about=) prefills category, area and time band; all stay editable,
 * and removing the "About" line also stops the tip being linked to the appeal or crime card.
 */
export function TipForm({ subject, defaultCategory }: { subject: TipSubject | null; defaultCategory?: TipCategory }) {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [linked, setLinked] = useState<TipSubject | null>(subject);
  const appeal = linked?.kind === "appeal" ? linked.id : null;
  const about = linked?.kind === "about" ? linked.id : null;
  const [staleLink, setStaleLink] = useState(false);
  const [category, setCategory] = useState<TipCategory | "">(defaultCategory ?? subject?.category ?? "");
  const [text, setText] = useState("");
  const [when, setWhen] = useState<TipWhen>(subject?.when ?? "");
  const [cell, setCell] = useState<string | null>(subject?.cell ?? null);
  const [items, setItems] = useState<Item[]>([]);
  const [blurFaces, setBlurFaces] = useState(true);
  const [mode, setMode] = useState<"anonymous" | "code">("anonymous");
  const [code] = useState(() => generateTipCode());
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [faceApi, setFaceApi] = useState(false);

  useEffect(() => setFaceApi(faceDetectionAvailable()), []);
  useEffect(() => () => items.forEach((i) => i.preview && URL.revokeObjectURL(i.preview)), [items]);

  const fullText = when ? `${text.trim()}\n\nWhen: ${when.toLowerCase()}` : text.trim();

  async function addFiles(list: FileList | null) {
    if (!list) return;
    setError(null);
    const next: Item[] = [];
    for (const f of Array.from(list).slice(0, MAX_FILES - items.length)) {
      if (f.size > MAX_FILE_BYTES) { setError(`${f.name} is larger than 15 MB.`); continue; }
      if (f.type.startsWith("image/")) {
        setBusy(`Cleaning ${f.name}…`);
        try {
          const c = await cleanImage(f, blurFaces && faceApi);
          next.push({
            name: f.name, kind: "image", blob: c.blob, preview: c.previewUrl, facesBlurred: c.facesBlurred,
            note: `Location and camera details removed${c.facesBlurred ? ` · ${c.facesFound} face${c.facesFound === 1 ? "" : "s"} blurred` : ""}`,
          });
        } catch {
          setError(`${f.name} could not be read as a photo.`);
        }
      } else if (f.type.startsWith("audio/")) {
        next.push({ name: f.name, kind: "audio", blob: f, preview: null, facesBlurred: false, note: "Audio file" });
      } else if (f.type.startsWith("video/")) {
        setError("Video can't be cleaned in the browser yet. Please send a still photo, or describe the footage and choose a tip code so police can ask for it.");
      } else {
        setError(`${f.name}: only photos and audio are accepted.`);
      }
    }
    setBusy(null);
    setItems((s) => s.concat(next));
  }

  const check1 = () => validateTip({ category, text: fullText, cell, followUp: false, code: null, passphrase: null, appeal, about });

  async function send() {
    setError(null);
    if (mode === "code" && pass !== pass2) return setError("The two passphrases do not match.");
    const input = { category, text: fullText, cell, followUp: mode === "code", code: mode === "code" ? code : null, passphrase: mode === "code" ? pass : null, appeal, about };
    const problem = validateTip(input);
    if (problem) return setError(problem);

    setBusy("Running a small security check…");
    const salt = generateTipCode() + generateTipCode();
    const pow = await solvePow(Date.now(), salt);
    setBusy("Sending…");
    const fd = new FormData();
    for (const [k, v] of tipFields({ ...input, pow })) fd.set(k, v);
    for (const it of items) {
      fd.append("files", it.blob, it.kind === "image" ? "photo.jpg" : "audio");
      fd.append("blurred", it.facesBlurred ? "1" : "0");
    }
    try {
      const r = await fetch("/api/public/tip", { method: "POST", body: fd, credentials: "omit", referrerPolicy: "no-referrer" });
      const j = await r.json();
      if (!j.ok) {
        setBusy(null);
        // The crime left the public map between page load and send (aged out of 90 days, or hidden).
        if (about && /unknown crime/i.test(j.error ?? "")) {
          setStaleLink(true);
          return setError("This crime is no longer on the public map. You can send the tip without the link.");
        }
        return setError(j.error ?? "Could not send the tip.");
      }
      try { sessionStorage.setItem("nexus-tip-sent", JSON.stringify({ code: mode === "code" ? code : null, week: j.received_week })); } catch { /* private mode */ }
      router.replace("/tip/sent");
    } catch {
      setBusy(null);
      setError("Network problem. Your tip was not sent; please try again.");
    }
  }

  const StepTab = ({ n, label }: { n: number; label: string }) => (
    <span className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${step === n ? "border-ink bg-ink text-bg shadow-sm" : step > n ? "border-signal bg-signal-soft text-signal" : "border-line bg-surface text-muted"}`}>{n} · {label}</span>
  );

  return (
    <div className="space-y-4">
      <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        In an emergency, call <strong>112</strong>. This form is not monitored around the clock.
      </p>
      <div className="flex flex-wrap gap-2"><StepTab n={1} label="What you saw" /><StepTab n={2} label="Files" /><StepTab n={3} label="Stay anonymous" /></div>
      {linked && (
        <p className="text-sm">
          About: <strong>{linked.label}</strong>
          <button type="button" className="ml-2 text-muted underline" aria-label={linked.kind === "appeal" ? "Remove the link to this appeal" : "Remove the link to this crime"}
            onClick={() => setLinked(null)}>✕ remove</button>
        </p>
      )}

      {step === 1 && (
        <section className="space-y-4 rounded-xl border border-line bg-surface p-5">
          <fieldset>
            <legend className="text-sm font-semibold">What is this about?</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {TIP_CATEGORIES.map((c) => (
                <button key={c} type="button" onClick={() => setCategory(c)} aria-pressed={category === c}
                  className={`rounded-full border px-3 py-1 text-sm ${category === c ? "border-signal bg-signal-soft" : "border-line"}`}>
                  {TIP_CATEGORY_LABEL[c]}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm">
            <span className="font-semibold">What did you see?</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={3900} autoFocus={!!subject}
              className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
              placeholder="Describe what you saw. Please don't include your own name, phone number or address." />
          </label>
          <label className="block text-sm">
            <span className="font-semibold">Roughly when?</span> <span className="text-muted">(optional)</span>
            <select value={when} onChange={(e) => setWhen(e.target.value as TipWhen)} className="mt-1 block rounded-md border border-line bg-bg px-3 py-2">
              {WHEN.map((w) => <option key={w} value={w}>{w || "Not sure"}</option>)}
            </select>
          </label>
          <div className="text-sm">
            <span className="font-semibold">Roughly where?</span> <span className="text-muted">(we only keep the area, not a point)</span>
            <div className="mt-1"><HexPicker cell={cell} onChange={setCell} /></div>
          </div>
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <button type="button" className="rounded-md bg-signal px-4 py-2 font-medium text-white"
            onClick={() => { const p = check1(); if (p) setError(p); else { setError(null); setStep(2); } }}>
            Next: add files
          </button>
        </section>
      )}

      {step === 2 && (
        <section className="space-y-4 rounded-xl border border-line bg-surface p-5">
          <label
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-line p-8 text-center text-sm"
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void addFiles(e.dataTransfer.files); }}
          >
            <span className="font-semibold">Drop photos or audio here, or tap to choose</span>
            <span className="mt-1 text-muted">Location and camera details are removed in your browser before upload. Up to {MAX_FILES} files.</span>
            <input type="file" multiple accept="image/*,audio/*" className="sr-only" onChange={(e) => void addFiles(e.target.files)} />
          </label>
          {faceApi ? (
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={blurFaces} onChange={(e) => setBlurFaces(e.target.checked)} /> Blur faces before sending</label>
          ) : (
            <p className="text-xs text-muted">Automatic face blurring isn&apos;t available in this browser. Avoid photos where people can be recognised.</p>
          )}
          {busy && <p className="text-sm text-muted">{busy}</p>}
          {items.length > 0 && (
            <ul className="grid gap-3 sm:grid-cols-3">
              {items.map((it, i) => (
                <li key={i} className="rounded-lg border border-line p-2 text-xs">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {it.preview ? <img src={it.preview} alt="Cleaned preview" className="h-28 w-full rounded object-cover" /> : <div className="grid h-28 place-items-center rounded bg-bg">♪ audio</div>}
                  <p className="mt-1 text-signal">✓ {it.note}</p>
                  <button type="button" className="text-muted underline" onClick={() => setItems((s) => s.filter((_, j) => j !== i))}>remove</button>
                </li>
              ))}
            </ul>
          )}
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button type="button" className="rounded-md px-3 py-2 text-sm text-muted" onClick={() => setStep(1)}>Back</button>
            <button type="button" disabled={!!busy} className="rounded-md bg-signal px-4 py-2 font-medium text-white disabled:opacity-60" onClick={() => { setError(null); setStep(3); }}>Next: privacy</button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="space-y-4 rounded-xl border border-line bg-surface p-5">
          <label className="flex items-start gap-3 text-sm">
            <input type="radio" name="mode" checked={mode === "anonymous"} onChange={() => setMode("anonymous")} className="mt-1" />
            <span><strong>Fully anonymous.</strong> No way for police to reply.</span>
          </label>
          <label className="flex items-start gap-3 text-sm">
            <input type="radio" name="mode" checked={mode === "code"} onChange={() => setMode("code")} className="mt-1" />
            <span><strong>Anonymous, with a tip code</strong> so I can read police replies.</span>
          </label>
          {mode === "code" && (
            <div className="space-y-3 rounded-lg bg-bg p-4">
              <p className="text-sm">Your tip code</p>
              <p className="font-mono text-3xl tracking-widest">{formatTipCode(code)}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <input type="password" autoComplete="new-password" placeholder="Choose a passphrase (8+ characters)" value={pass} onChange={(e) => setPass(e.target.value)} className="rounded-md border border-line bg-surface px-3 py-2 text-sm" />
                <input type="password" autoComplete="new-password" placeholder="Repeat the passphrase" value={pass2} onChange={(e) => setPass2(e.target.value)} className="rounded-md border border-line bg-surface px-3 py-2 text-sm" />
              </div>
              <p className="text-xs text-muted">Keep the code and passphrase; they cannot be recovered. Don&apos;t use a password you use elsewhere.</p>
            </div>
          )}
          <p className="text-xs text-muted">
            We never store your IP address, device, phone number, email or exact time. Your tip is kept with the week it arrived and, if you chose one, the area you picked (between about 0.015 and 0.7 km²), never an exact point.
          </p>
          <div className="rounded-lg border border-line p-3 text-sm">
            <p className="font-semibold">Review</p>
            <p className="mt-1">{category ? TIP_CATEGORY_LABEL[category] : "—"} · {items.length} file{items.length === 1 ? "" : "s"} · {cell ? "area chosen" : "no area"} · {mode === "code" ? "with tip code" : "no replies"}</p>
            <p className="mt-1 line-clamp-3 whitespace-pre-line text-muted">{fullText}</p>
          </div>
          {busy && <p className="text-sm text-muted">{busy}</p>}
          {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button type="button" className="rounded-md px-3 py-2 text-sm text-muted" onClick={() => setStep(2)}>Back</button>
            <button type="button" disabled={!!busy} className="rounded-md bg-signal px-4 py-2 font-medium text-white disabled:opacity-60" onClick={() => void send()}>Send tip</button>
            {staleLink && linked && (
              <button type="button" className="rounded-md border border-line px-3 py-2 text-sm"
                onClick={() => { setLinked(null); setStaleLink(false); setError(null); }}>Remove the link</button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
