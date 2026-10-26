import Link from "next/link";
import { CrimeCardView } from "@/components/public/CrimeCardView";
import { getPublicCrime } from "@/lib/publicData";
import { cardTitle, mapHref, parseMapState } from "@/lib/publicCards";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: { publicId: string } }) {
  const card = await getPublicCrime(params.publicId);
  return { title: card ? `${cardTitle(card)} · Crime map · Nexus Chennai` : "Crime map · Nexus Chennai" };
}

/**
 * One public crime (0007_11 public_crime): the same safe fields as its card. "Back to map" rebuilds the map URL
 * from the carried state (hex, window, type, position), re-validated, so it restores the view the visitor left.
 */
export default async function PublicCrimePage({ params, searchParams }: {
  params: { publicId: string };
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const state = parseMapState(searchParams);
  const card = await getPublicCrime(params.publicId);
  const back = mapHref(card && !state.hex ? { ...state, hex: card.cell } : state);
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Link href={back} className="inline-block rounded-lg border border-line px-3 py-1.5 text-sm">← Back to map</Link>
      {card ? (
        <>
          <CrimeCardView card={card} headingLevel={2} />
          <p className="text-xs text-muted">
            Shown without exact time, place, people or case numbers. The area is the police station locality nearest this
            hexagon. Seen something? Sharing a tip is anonymous: no account, name or phone number.
          </p>
        </>
      ) : (
        <div className="rounded-xl border border-line bg-surface p-4">
          <h1 className="text-xl font-bold">This crime is not on the public map</h1>
          <p className="mt-1 text-sm text-muted">It may be older than 90 days, or too few similar crimes were reported nearby to show it.</p>
        </div>
      )}
    </div>
  );
}
