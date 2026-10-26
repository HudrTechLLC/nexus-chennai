import Link from "next/link";
import { consoleCellMapHref } from "@/lib/consoleArea";
import { consoleServerClient } from "@/lib/supabase/server";
import { PUBLIC_TIPS_EMPTY, SOURCE_LABEL } from "@/lib/publicTips";
import { fetchPublicTips } from "@/lib/publicTipsData";
import { TIP_CATEGORY_LABEL, tipAreaLabel } from "@/lib/tips";

/**
 * "From the public" (WS3-28): tips tied to these crimes, an evidence feed next to the link evidence.
 * Shows only week, category, status and the area cell: tip text stays on the tip page (untrusted input).
 */
export async function PublicTipsBlock({ crimeIds, label }: { crimeIds: string[]; label: (crimeId: string) => string }) {
  const feed = await fetchPublicTips(consoleServerClient(), crimeIds);
  return (
    <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="from-public">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="from-public" className="text-lg font-semibold">From the public</h2>
        <span className="text-xs text-muted">Tips tied to these cases by appeal, crime card or officer review</span>
      </div>
      {feed.tips.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{PUBLIC_TIPS_EMPTY}</p>
      ) : (
        <ul className="mt-3 divide-y divide-line text-sm">
          {feed.tips.map((t) => {
            const map = consoleCellMapHref(t.approx_cell_fine || t.approx_cell);
            return (
              <li key={t.tip_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                <Link href={`/console/tips/${encodeURIComponent(t.tip_id)}`} className="font-mono text-xs underline-offset-2 hover:underline">{t.tip_id}</Link>
                <span className="font-mono text-xs tabular-nums text-muted">{t.received_week}</span>
                <span>{TIP_CATEGORY_LABEL[t.category] ?? t.category}</span>
                <span className="rounded-full border border-line px-2 py-0.5 text-xs">{t.status}</span>
                {map
                  ? <Link href={map} className="text-xs text-accent underline-offset-2 hover:underline">{tipAreaLabel(t)} on the map</Link>
                  : <span className="text-xs text-muted">no area</span>}
                <span className="w-full text-xs text-muted">
                  {t.links.map((l) => `${SOURCE_LABEL[l.source]} · ${label(l.crimeId)}`).join(" ; ")}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {(feed.quarantined > 0 || feed.unreadableCrimes > 0) && (
        <p className="mt-3 text-xs text-muted">
          {feed.quarantined > 0 && <>{feed.quarantined} tip{feed.quarantined === 1 ? "" : "s"} quarantined by Tip Guard, not shown (see the tips queue). </>}
          {feed.unreadableCrimes > 0 && <>{feed.unreadableCrimes} case{feed.unreadableCrimes === 1 ? "" : "s"} at other stations {feed.unreadableCrimes === 1 ? "is" : "are"} not checked for tips.</>}
        </p>
      )}
    </section>
  );
}
