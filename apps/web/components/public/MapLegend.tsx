import { densityGradient } from "@/lib/publicMapTheme";

/**
 * Key for the public crime map: the density ramp (relative to the busiest visible hexagon), the open-appeal
 * outline and the selected outline. The colours are the map's own (publicMapTheme), the outlines use the same
 * --signal / --ink tokens the map reads through MAP_INK.
 */
export function MapLegend({ minCount }: { minCount: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-line bg-surface px-4 py-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-muted">Fewer reports</span>
        <span aria-hidden="true" className="h-3 w-28 rounded-full border border-line" style={{ background: densityGradient(), opacity: 0.85 }} />
        <span className="text-muted">More</span>
      </div>
      <div className="flex items-center gap-2">
        <Hex className="fill-transparent stroke-[var(--signal)]" />
        <span>Open police appeal</span>
      </div>
      <div className="flex items-center gap-2">
        <Hex className="fill-transparent stroke-[var(--ink)]" />
        <span>Selected area</span>
      </div>
      <p className="text-muted">Hidden: areas with fewer than {minCount} reports</p>
    </div>
  );
}

function Hex({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="h-5 w-5">
      <path d="M12 2.5l8.2 4.75v9.5L12 21.5l-8.2-4.75v-9.5z" strokeWidth={2.4} strokeLinejoin="round" className={className} />
    </svg>
  );
}
