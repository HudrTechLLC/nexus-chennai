import { consoleServerClient } from "@/lib/supabase/server";
import { attachable, BLUR_LABEL, MAX_STILLS, parseImages, publicStillUrl, STILL_ALT, type EvidenceRow } from "@/lib/appealStills";
import { AttachButton, DetachButton } from "./StillsButtons";

/**
 * Appeal editor section: pick case stills to publish as blurred copies (PUB-02).
 * Originals are shown to the officer only, through short-lived signed URLs under their own RLS;
 * the public only ever gets the blurred copy.
 */
export async function StillsPanel({ appealId, crimeId, images: raw, status, canWrite }: {
  appealId: string; crimeId: string | null; images: unknown; status: string; canWrite: boolean;
}) {
  const sb = consoleServerClient();
  const images = parseImages(raw);
  const { data } = crimeId
    ? await sb.from("evidence_media").select("evidence_id, crime_id, kind, storage_path, captured_at, created_at").eq("crime_id", crimeId).order("created_at")
    : { data: [] };
  const evidence = ((data ?? []) as EvidenceRow[]).filter((e) => attachable(e, crimeId));
  const signed = evidence.length
    ? (await sb.storage.from("evidence").createSignedUrls(evidence.map((e) => e.storage_path), 300)).data ?? []
    : [];
  const thumb = new Map(signed.map((s) => [s.path, s.signedUrl]));
  const attachedIds = new Set(images.map((i) => i.evidence_id));
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const open = status !== "withdrawn";

  return (
    <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="stills">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="stills" className="font-semibold">Blurred stills <span className="text-sm font-normal text-muted">· {images.length} of {MAX_STILLS}</span></h2>
        <span className="text-xs text-accent">{BLUR_LABEL}</span>
      </div>

      {images.length > 0 && (
        <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {images.map((i) => (
            <li key={i.path} className="space-y-1">
              {/* Public blurred copy; plain img because it is a small fixed JPEG in a console-only view. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={publicStillUrl(base, i.path)} alt={STILL_ALT} width={i.width} height={i.height} className="aspect-video w-full rounded-md border border-line object-cover" />
              {canWrite && open && <DetachButton appealId={appealId} path={i.path} />}
            </li>
          ))}
        </ul>
      )}

      {!canWrite ? (
        <p className="mt-3 text-sm text-muted">Only officers of this case&apos;s station, supervisors and admins can attach stills.</p>
      ) : !open ? (
        <p className="mt-3 text-sm text-muted">This appeal is withdrawn; its public stills were removed.</p>
      ) : evidence.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          This case has no JPEG or PNG stills yet. Upload one on the case&apos;s Evidence tab, then attach it here. Only a blurred copy is ever published.
        </p>
      ) : (
        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-2 text-xs text-muted">Case stills (originals, visible to police only). Attaching publishes a blurred copy, never the original.</p>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {evidence.map((e) => (
              <li key={e.evidence_id} className="space-y-1">
                {thumb.get(e.storage_path) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={thumb.get(e.storage_path)} alt={`Case still ${e.evidence_id}`} className="aspect-video w-full rounded-md border border-line object-cover" />
                ) : (
                  <div className="grid aspect-video w-full place-items-center rounded-md border border-dashed border-line text-xs text-muted">no preview</div>
                )}
                <p className="truncate font-mono text-[11px] text-muted">{e.evidence_id} · {e.kind.replace("_", " ")}</p>
                {attachedIds.has(e.evidence_id)
                  ? <p className="text-xs text-signal">Attached</p>
                  : <AttachButton appealId={appealId} evidenceId={e.evidence_id} disabled={images.length >= MAX_STILLS} />}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
