import { constellation, STATUS_LABEL, type SeriesStatus } from "@/lib/series";

/** Constellation thumbnail: member cases as stars in their H3 cells, north up (spec G2 series list). */
export function Constellation({ cells, w = 120, h = 72 }: { cells: string[]; w?: number; h?: number }) {
  const { dots } = constellation(cells, w, h);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0 rounded-lg bg-bg" role="img"
      aria-label={dots.length ? `${cells.length} cases in ${dots.length} map cells` : "no mapped cases"}>
      {dots.length > 1 && (
        <polyline points={dots.map((d) => `${d.x},${d.y}`).join(" ")} fill="none" stroke="var(--line)" strokeWidth={1} />
      )}
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={Math.min(6, 2 + d.n)} fill="var(--signal)" fillOpacity={0.85} />
      ))}
      {dots.length === 0 && <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize={10} fill="var(--muted)">no cells</text>}
    </svg>
  );
}

export function SeriesStatusPill({ status }: { status: SeriesStatus }) {
  const cls = status === "confirmed" ? "border-signal text-signal" : status === "closed" ? "border-line text-muted" : "border-accent text-accent";
  return <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${cls}`}>{STATUS_LABEL[status] ?? status}</span>;
}
