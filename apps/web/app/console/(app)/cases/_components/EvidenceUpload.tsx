"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { EVIDENCE_KINDS } from "@/lib/evidence";

const input = "rounded-md border border-line bg-bg px-2 py-1.5 text-sm";

/**
 * Drag-and-drop evidence (or audio statement) upload for one case. Files go unchanged to the
 * route handler, which checks the bytes, hashes them and stores them privately.
 */
export function EvidenceUpload({ crimeId, target = "evidence" }: { crimeId: string; target?: "evidence" | "statement" }) {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<string>(target === "statement" ? "audio" : "cctv_still");
  const [camera, setCamera] = useState("");
  const [captured, setCaptured] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [over, setOver] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const router = useRouter();

  async function send() {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    const fd = new FormData();
    fd.set("file", file);
    fd.set("target", target);
    fd.set("kind", kind);
    if (camera) fd.set("camera_id", camera);
    if (captured) fd.set("captured_at", captured);
    try {
      const r = await fetch(`/console/cases/${encodeURIComponent(crimeId)}/evidence/upload`, { method: "POST", body: fd });
      const j = (await r.json().catch(() => ({}))) as { ok?: boolean; error?: string; sha256?: string };
      if (r.ok && j.ok) {
        setMsg({ ok: true, text: `Saved. sha256 ${j.sha256?.slice(0, 16)}…` });
        setFile(null);
        setCamera("");
        setCaptured("");
        router.refresh();
      } else setMsg({ ok: false, text: j.error ?? `Upload failed (${r.status}).` });
    } catch {
      setMsg({ ok: false, text: "Network error. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed border-line p-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => picker.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && picker.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); setFile(e.dataTransfer.files?.[0] ?? null); }}
        className={`cursor-pointer rounded-md p-4 text-center text-sm ${over ? "bg-signal-soft" : "bg-bg"}`}
      >
        {file ? <span>{file.name} · {(file.size / 1024).toFixed(0)} KB</span> : (
          <span className="text-muted">{target === "statement" ? "Drop an audio statement here, or click to choose (≤ 4 MB)" : "Drop a photo, CCTV still or clip, scan, PDF or audio file here, or click to choose (≤ 4 MB)"}</span>
        )}
        <input ref={picker} type="file" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          accept={target === "statement" ? "audio/*" : "image/jpeg,image/png,image/webp,application/pdf,video/mp4,audio/*"} />
      </div>
      {target === "evidence" && (
        <div className="flex flex-wrap gap-2">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={input} aria-label="Kind">
            {EVIDENCE_KINDS.map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
          </select>
          <input value={camera} onChange={(e) => setCamera(e.target.value)} placeholder="camera id (optional)" className={input} />
          <label className="flex items-center gap-1 text-xs text-muted">captured
            <input type="datetime-local" value={captured} onChange={(e) => setCaptured(e.target.value)} className={input} />
          </label>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" disabled={!file || busy} onClick={send} className="rounded-md bg-ink px-3 py-1.5 text-sm font-semibold text-bg disabled:opacity-50">
          {busy ? "Uploading…" : target === "statement" ? "Add audio statement" : "Add evidence"}
        </button>
        <span className="text-xs text-muted">Stored unchanged with its sha256; the capture time is read from the photo when you leave it blank.</span>
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
    </div>
  );
}
