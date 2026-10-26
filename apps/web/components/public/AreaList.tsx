import type { AreaRow } from "@/lib/publicArea";

/**
 * "Areas with crimes" under the public map: the keyboard (and screen-reader) way to the crime cards,
 * since hexagons on the map are mouse/touch only. One button per hexagon that has cards; Enter or a
 * click opens the same card panel a hexagon click opens. Collapsible, open by default.
 */
export function AreaList({ rows, selected, onOpen }: { rows: AreaRow[]; selected: string | null; onOpen: (cell: string) => void }) {
  if (rows.length === 0) return null;
  return (
    <details open className="rounded-xl border border-line bg-surface">
      <summary className="cursor-pointer select-none px-4 py-2 text-sm font-semibold">
        Areas with crimes <span className="font-normal text-muted">({rows.length})</span>
      </summary>
      <ul aria-label="Areas with crimes" className="max-h-72 divide-y divide-line overflow-y-auto border-t border-line">
        {rows.map((r) => (
          <li key={r.cell}>
            <button
              type="button"
              data-cell={r.cell}
              aria-current={selected === r.cell ? "true" : undefined}
              aria-label={`Open cards for ${r.area}: ${r.cards} ${r.cards === 1 ? "crime" : "crimes"}${r.appeal ? ", open police appeal" : ""}`}
              onClick={() => onOpen(r.cell)}
              className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm hover:bg-bg focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal aria-[current=true]:bg-signal-soft"
            >
              <span className="min-w-0">
                <span className="font-medium">{r.area}</span>
                <span className="text-muted"> · {r.cards} {r.cards === 1 ? "crime" : "crimes"}</span>
                {r.appeal && <span className="ml-2 rounded-full border border-line px-1.5 py-0.5 text-xs text-muted">appeal</span>}
              </span>
              <span className="shrink-0 font-medium text-signal">Open cards</span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default AreaList;
