"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { consoleBrowserClient } from "@/lib/supabase/browser";
import { CAT_COLOUR, CAT_LABEL, type MapCrime } from "@/lib/pulse";
import type { Links } from "./usePulseData";

type Detail = {
  fir_no: string; address: string | null; narrative: string | null; occurred_from: string; weapon: string | null;
  mo: Record<string, unknown> | null; visual_tags: string[];
};

/** Side drawer for a clicked dot (spec G3): summary, MO chips, linked cases, open case, show trail. */
export function CrimeDrawer({ crime, links, byId, onClose, onShowTrail }: {
  crime: MapCrime; links: Links; byId: Map<string, MapCrime>; onClose: () => void; onShowTrail: () => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    const sb = consoleBrowserClient();
    Promise.all([
      sb.from("crimes").select("fir_no, address, narrative, occurred_from, weapon").eq("crime_id", crime.id).maybeSingle(),
      sb.from("crime_features").select("mo, visual_tags").eq("crime_id", crime.id).maybeSingle(),
    ]).then(([c, f]) => {
      if (cancelled || !c.data) return;
      setDetail({ ...c.data, mo: f.data?.mo ?? null, visual_tags: f.data?.visual_tags ?? [] } as Detail);
    });
    return () => { cancelled = true; };
  }, [crime.id]);

  const related = links.alerts.filter((a) => a.crimes.includes(crime.id));
  const series = links.series.filter((s) => s.members.includes(crime.id));
  const moChips = detail?.mo
    ? Object.entries(detail.mo).flatMap(([k, v]) => (v == null || k === "offender_count" ? [] : Array.isArray(v) ? v.map(String) : [String(v)]))
    : [];

  return (
    <aside className="absolute inset-y-0 right-0 z-10 w-full max-w-sm overflow-y-auto border-l border-line bg-surface p-4 text-sm shadow-2xl">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${CAT_COLOUR[crime.cat].join(",")})` }} />
            {CAT_LABEL[crime.cat]} · {crime.sub?.replaceAll("_", " ") ?? crime.category}
          </p>
          <h2 className="text-lg font-bold">{detail ? `${crime.st.replace(/^PS-/, "")} ${detail.fir_no}` : crime.id}</h2>
        </div>
        <button onClick={onClose} className="rounded-md px-2 py-1 text-muted hover:bg-bg" aria-label="Close">✕</button>
      </div>

      <dl className="mt-3 grid grid-cols-[6rem_1fr] gap-y-1">
        <dt className="text-muted">When</dt>
        <dd>{new Date(crime.t).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })}</dd>
        <dt className="text-muted">Station</dt><dd>{crime.st}</dd>
        <dt className="text-muted">Status</dt><dd>{crime.status.replaceAll("_", " ")}</dd>
        <dt className="text-muted">Severity</dt><dd>{crime.sev} / 5</dd>
        {detail?.address && (<><dt className="text-muted">Place</dt><dd>{detail.address}</dd></>)}
        {detail?.weapon && (<><dt className="text-muted">Weapon</dt><dd>{detail.weapon}</dd></>)}
      </dl>

      {detail?.narrative && <p className="mt-3 line-clamp-5 text-muted">{detail.narrative}</p>}

      {(moChips.length > 0 || (detail?.visual_tags.length ?? 0) > 0) && (
        <div className="mt-3 flex flex-wrap gap-1">
          {moChips.map((t, i) => <span key={`m${i}`} className="rounded bg-bg px-1.5 py-0.5 text-xs">{t.replaceAll("_", " ")}</span>)}
          {detail?.visual_tags.map((t, i) => <span key={`v${i}`} className="rounded bg-accent-soft px-1.5 py-0.5 text-xs">{t}</span>)}
        </div>
      )}

      <h3 className="mt-4 font-semibold">Linked cases</h3>
      {related.length === 0 ? <p className="text-muted">None.</p> : (
        <ul className="mt-1 space-y-1">
          {related.map((a) => (
            <li key={a.id}>
              <Link href={`/console/alerts/${encodeURIComponent(a.id)}`} className="text-signal hover:underline">{a.id}</Link>
              <span className="text-muted"> · {a.status} · {Math.round(a.score * 100)}% · with </span>
              {a.crimes.filter((x) => x !== crime.id).map((x) => byId.get(x) ? x : `${x} (other station)`).join(", ")}
            </li>
          ))}
        </ul>
      )}

      {series.length > 0 && (
        <>
          <h3 className="mt-4 font-semibold">Series</h3>
          <ul className="mt-1">
            {series.map((s) => (
              <li key={s.id}><Link href={`/console/series/${encodeURIComponent(s.id)}`} className="text-signal hover:underline">{s.name}</Link> · {s.members.length} cases</li>
            ))}
          </ul>
        </>
      )}

      <div className="mt-5 flex gap-2">
        <Link href={`/console/cases/${encodeURIComponent(crime.id)}`} className="rounded-md bg-signal px-3 py-1.5 text-white">Open case</Link>
        <button onClick={onShowTrail} title="ANPR reads of the offender vehicle plate within 6 hours" className="rounded-md border border-line px-3 py-1.5">Show trail</button>
      </div>
    </aside>
  );
}
