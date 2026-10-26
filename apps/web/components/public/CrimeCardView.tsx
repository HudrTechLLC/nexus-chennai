import Link from "next/link";
import { STATUS_LABEL, cardTitle, labelOf, tipHref, weekLabel, type CrimeCard } from "@/lib/publicCards";

/**
 * One public crime card (0007_11): type, area, week and time of day, status, pattern flag, the allow-listed
 * MO sentence and any open appeal. Public fields only: no exact time, place, people or case numbers.
 */
export function CrimeCardView({ card, detailHref, headingLevel = 3 }: { card: CrimeCard; detailHref?: string; headingLevel?: 2 | 3 }) {
  const H = headingLevel === 2 ? "h2" : "h3";
  return (
    <article className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <H className={headingLevel === 2 ? "text-xl font-bold" : "font-semibold"}>
        {detailHref ? <Link href={detailHref} className="hover:underline">{cardTitle(card)}</Link> : cardTitle(card)}
      </H>
      <p className="text-sm text-muted">
        {card.area ?? "This area"} · {weekLabel(card.week)} · {labelOf(card.time_window)}
      </p>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-full border border-line px-2 py-0.5">{STATUS_LABEL[card.status] ?? "Open"}</span>
        {card.in_pattern && (
          <span className="rounded-full border border-signal bg-signal-soft px-2 py-0.5">Part of a pattern of similar crimes</span>
        )}
      </div>
      {card.mo_summary && <p className="text-sm">{card.mo_summary}</p>}
      {card.appeals.length > 0 && (
        <ul className="space-y-1 text-sm">
          {card.appeals.map((a) => (
            <li key={a.id}>
              Police appeal: <Link href={`/appeals/${a.id}`} className="font-medium underline">{a.title}</Link>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2 pt-1 text-sm">
        {detailHref && <Link href={detailHref} className="rounded-lg border border-line px-3 py-1.5">Details</Link>}
        <Link href={tipHref(card.public_id)} className="rounded-lg border border-signal bg-signal-soft px-3 py-1.5 font-medium">
          Share a tip about this
        </Link>
      </div>
    </article>
  );
}

export default CrimeCardView;
