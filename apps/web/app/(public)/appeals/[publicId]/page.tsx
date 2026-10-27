import Link from "next/link";
import { notFound } from "next/navigation";
import Image from "next/image";
import { getAppeal } from "@/lib/publicData";
import { APPEAL_IMAGE_ALT, appealImageUrl } from "@/lib/appealImages";
import { appealTipHref, crimeMapHref, publicCell } from "@/lib/publicArea";
import { AppealAreaMap } from "@/components/public/AppealAreaMap";
import { CategoryBadge, CategoryMark } from "@/components/public/CategoryIcon";
import { labelOf } from "@/lib/publicCards";
import { buttonClass } from "@/components/ui";

export const revalidate = 60;

export default async function AppealDetail({ params }: { params: { publicId: string } }) {
  const a = await getAppeal(decodeURIComponent(params.publicId));
  if (!a) notFound();
  const stills = (a.images ?? []).flatMap((img) => {
    const url = appealImageUrl(process.env.NEXT_PUBLIC_SUPABASE_URL, img.path);
    return url ? [{ url, width: img.width ?? 640, height: img.height ?? 360 }] : [];
  });
  const cell = publicCell(a.cell);
  const mapHref = crimeMapHref(cell);
  return (
    <article className="mx-auto max-w-2xl space-y-5">
      <Link href="/appeals" className="text-sm text-muted hover:text-ink">← All appeals</Link>
      <header className="flex items-start gap-4 rounded-2xl border border-line bg-gradient-to-br from-surface to-signal-soft p-5 sm:p-6">
        <CategoryMark category={a.category} size="lg" />
        <div className="min-w-0">
          {a.category && <CategoryBadge category={a.category} label={labelOf(a.category)} />}
          <p className="mt-2 font-mono text-xs uppercase tracking-widest text-accent">{a.area} · week {a.week} · {a.time_window}</p>
          <h1 className="mt-1 text-3xl font-bold">{a.title}</h1>
        </div>
      </header>
      <p className="text-lg">{a.summary}</p>
      {a.looking_for.length > 0 && (
        <section className="rounded-xl border border-[color-mix(in_srgb,var(--signal)_35%,transparent)] bg-signal-soft p-5">
          <h2 className="font-semibold">What police are looking for</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">{a.looking_for.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </section>
      )}
      {stills.length > 0 && (
        <section aria-label="Blurred stills" className="space-y-2">
          <div className="grid gap-3 sm:grid-cols-2">
            {stills.map((s) => (
              <figure key={s.url} className="overflow-hidden rounded-xl border border-line bg-surface">
                <Image src={s.url} alt={APPEAL_IMAGE_ALT} width={s.width} height={s.height}
                  sizes="(min-width: 640px) 336px, 100vw" className="h-auto w-full" />
              </figure>
            ))}
          </div>
          <p className="text-xs text-muted">Whole images are blurred before publishing, so no face or plate can be read.</p>
        </section>
      )}
      {cell && (
        <section aria-labelledby="where" className="space-y-2 rounded-xl border border-line bg-surface p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="where" className="font-semibold">Where it happened</h2>
            {mapHref && <Link href={mapHref} className="text-sm text-accent underline-offset-2 hover:underline">See on crime map →</Link>}
          </div>
          <AppealAreaMap cell={cell} />
          <p className="text-xs text-muted">{a.area}. Shown as an area of about 0.7 km², never an exact spot.</p>
        </section>
      )}
      <section className="rounded-xl border border-line bg-surface p-5 text-sm">
        <h2 className="font-semibold">Timeline</h2>
        <p className="mt-1 text-muted">Happened in week {a.week} ({a.time_window.toLowerCase()}). Published {a.published_at ? new Date(a.published_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "recently"}. {a.tip_count} tip{a.tip_count === 1 ? "" : "s"} received.</p>
      </section>
      <div className="flex flex-wrap gap-3">
        <Link href={appealTipHref(a.id)} className={buttonClass()}>Add a tip about this appeal</Link>
        <Link href={appealTipHref(a.id, "cctv")} className={buttonClass({ variant: "secondary" })}>I have CCTV</Link>
      </div>
      <p className="text-xs text-muted">In an emergency, call 112.</p>
    </article>
  );
}
