import Link from "next/link";
import { CrimeCardView } from "@/components/public/CrimeCardView";
import { crimeHref, labelOf, mapHref, type HexCrimes, type MapState } from "@/lib/publicCards";

/**
 * The cards for the selected hexagon: a panel on the left of the map on desktop, a bottom sheet on mobile.
 * Under the >=3 rule a hexagon (or a crime type in it) may have no cards; the panel says why in plain words.
 */
export function HexPanel({ state, hex, error, minCount }: { state: MapState; hex: HexCrimes | null; error: string | null; minCount: number }) {
  const close = mapHref({ ...state, hex: null });
  const cards = hex?.cards ?? [];
  return (
    <aside
      aria-label="Crimes in the selected area"
      className="fixed inset-x-0 bottom-0 z-20 max-h-[60vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface p-4 shadow-lg
                 md:absolute md:inset-auto md:bottom-3 md:left-3 md:top-3 md:max-h-none md:w-96 md:rounded-xl md:border"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{hex?.area ?? "This area"}</h2>
          <p className="text-xs text-muted">
            Last {state.days} days{state.type ? ` · ${labelOf(state.type)}` : ""} · {cards.length} {cards.length === 1 ? "crime" : "crimes"} shown
          </p>
        </div>
        <Link href={close} scroll={false} className="rounded-lg border border-line px-2 py-1 text-sm" aria-label="Close the list">✕</Link>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {!error && cards.length === 0 && (
        <p className="text-sm text-muted">
          No individual crimes are shown here. To protect victims, a crime appears only when at least {minCount} of the same
          type were reported in this hexagon in the period.
        </p>
      )}
      <div className="space-y-3">
        {cards.map((c) => (
          <CrimeCardView key={c.public_id} card={c} detailHref={crimeHref(c.public_id, state)} />
        ))}
      </div>
    </aside>
  );
}

export default HexPanel;
