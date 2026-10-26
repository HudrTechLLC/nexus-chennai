import Link from "next/link";
import { humanise } from "@/lib/cases";
import { SIMILAR_WEIGHTS, type SimilarHit } from "@/lib/similar";

/** Look-alike cases with the tags they share (case file panel and search "similar MO" mode). */
export function SimilarList({ hits, names }: { hits: SimilarHit[]; names: Record<string, string> }) {
  if (hits.length === 0) return <p className="text-muted">No other case shares its MO or visual tags yet.</p>;
  return (
    <div className="space-y-2">
      <ul className="divide-y divide-line">
        {hits.map((h) => (
          <li key={h.crime_id} className="py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <Link href={`/console/cases/${encodeURIComponent(h.crime_id)}`} className="font-mono text-signal hover:underline">{h.crime_id}</Link>
              <span className="font-mono text-xs" title="Look-alike score, not a link score">{Math.round(h.score * 100)}</span>
            </div>
            <p className="text-xs text-muted">{(names[h.station_id] ?? h.station_id).replace(/^PS-/, "")} · {humanise(h.category)}{h.sub_type ? ` · ${humanise(h.sub_type)}` : ""}{h.week ? ` · ${h.week}` : ""}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {h.sharedMo.map((t) => <span key={`m-${t}`} className="rounded bg-bg px-1.5 py-0.5 text-xs">{humanise(t)}</span>)}
              {h.sharedVisual.map((t) => <span key={`v-${t}`} className="rounded bg-signal-soft px-1.5 py-0.5 text-xs text-signal">{humanise(t)}</span>)}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted">
        Look-alike score = {SIMILAR_WEIGHTS.mo * 100}% shared MO tags + {SIMILAR_WEIGHTS.visual * 100}% shared visual tags + {SIMILAR_WEIGHTS.subType * 100}% same sub-type + {SIMILAR_WEIGHTS.cell * 100}% same area.
        It helps browsing; link alerts come from the pipeline&apos;s scoring and Skeptic review.
      </p>
    </div>
  );
}
