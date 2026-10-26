import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit } from "@/lib/alertsData";
import { canWriteCase, describe, humanise } from "@/lib/cases";
import type { Evidence } from "@/lib/casesData";
import { EvidenceUpload } from "../../_components/EvidenceUpload";

export const dynamic = "force-dynamic";

function fmt(at: string | null | undefined) {
  if (!at) return "—";
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

type Custody = { at?: string; by?: string; action?: string; sha256?: string };

/** Spec G2 /console/cases/[crimeId]/evidence: gallery with vision tags, plate reads and custody chain. */
export default async function EvidencePage({ params }: { params: { crimeId: string } }) {
  const officer = await requireOfficer("all");
  const sb = consoleServerClient();
  const crimeId = decodeURIComponent(params.crimeId);
  const { data: crime } = await sb.from("crimes").select("crime_id, station_id, fir_no").eq("crime_id", crimeId).maybeSingle();
  if (!crime) notFound();
  await audit(sb, "view_evidence", "crime", crimeId);

  const { data } = await sb.from("evidence_media")
    .select("evidence_id, kind, storage_path, sha256, captured_at, camera_id, uploaded_by, vision, custody, created_at")
    .eq("crime_id", crimeId).order("captured_at", { ascending: true, nullsFirst: false });
  const items = (data ?? []) as Evidence[];
  // Short-lived links, signed as this officer (storage policy: can_read_crime). Seeded rows may point at
  // files that live outside the bucket; those simply show without a preview.
  const signed = items.length
    ? (await sb.storage.from("evidence").createSignedUrls(items.map((e) => e.storage_path), 600)).data ?? []
    : [];
  const urlFor = Object.fromEntries(signed.filter((s) => s.signedUrl && s.path).map((s) => [s.path as string, s.signedUrl]));
  const canWrite = canWriteCase(officer.role, officer.stationId, crime.station_id);

  return (
    <div className="space-y-4">
      <Link href={`/console/cases/${encodeURIComponent(crimeId)}`} className="text-sm text-muted hover:text-ink">← Case {crime.fir_no}</Link>
      <h1 className="text-2xl font-bold">Evidence <span className="font-mono text-sm text-muted">{crimeId}</span></h1>

      {canWrite && <EvidenceUpload crimeId={crimeId} />}

      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">No evidence yet.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((e) => {
            const url = urlFor[e.storage_path];
            const v = (e.vision ?? {}) as { tags?: string[]; plates?: string[]; model?: string; summary?: string };
            return (
              <article key={e.evidence_id} className="overflow-hidden rounded-xl border border-line bg-surface">
                <div className="grid aspect-video place-items-center bg-bg">
                  {url && /\.(jpg|png|webp)$/.test(e.storage_path) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={url} alt={`${humanise(e.kind)} ${e.evidence_id}`} className="h-full w-full object-contain" />
                  ) : url && /\.mp4$/.test(e.storage_path) ? (
                    <video src={url} controls className="h-full w-full" />
                  ) : url && /\.(mp3|m4a|ogg|webm|wav)$/.test(e.storage_path) ? (
                    <audio src={url} controls className="w-11/12" />
                  ) : url ? (
                    <a href={url} target="_blank" rel="noreferrer" className="text-sm text-signal hover:underline">Open document</a>
                  ) : <span className="text-xs text-muted">No preview</span>}
                </div>
                <div className="space-y-2 p-4 text-sm">
                  <p className="font-semibold">{humanise(e.kind)}{e.camera_id ? ` · camera ${e.camera_id}` : ""}</p>
                  <p className="text-xs text-muted">Captured {fmt(e.captured_at)} · added {fmt(e.created_at)}</p>
                  {v.tags?.length ? <div className="flex flex-wrap gap-1">{v.tags.map((t) => <span key={t} className="rounded bg-bg px-1.5 py-0.5 text-xs">{t}</span>)}</div> : (
                    <p className="text-xs text-muted">Vision tags: not extracted yet.</p>
                  )}
                  {v.plates?.length ? <p className="text-xs">Plate reads: <span className="font-mono">{v.plates.join(", ")}</span></p> : null}
                  {v.summary ? <p className="text-xs">{v.summary}</p> : null}
                  {v.model ? <p className="text-xs text-muted">Vision model {v.model}</p> : null}
                  {!v.tags && Object.keys(v).length > 0 && <p className="text-xs text-muted">{describe(v as Record<string, unknown>)}</p>}
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted">Custody chain ({e.custody.length})</summary>
                    <p className="mt-1 break-all font-mono">sha256 {e.sha256}</p>
                    <ol className="mt-1 space-y-1">
                      {(e.custody as Custody[]).map((c, i) => (
                        <li key={i}>{fmt(c.at)} · {c.action ?? "step"}{c.sha256 && c.sha256 !== e.sha256 ? " · HASH MISMATCH" : ""}</li>
                      ))}
                    </ol>
                  </details>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
