import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { parseTipTab, statusesFor, TIP_CATEGORY_LABEL, TIP_TAB_LABEL, TIP_TABS, type TipRow } from "@/lib/tips";
import { GuardBadges, UntrustedText } from "@/components/console/tips/TipBits";
import { TipsLive } from "@/components/console/tips/TipsLive";

export const dynamic = "force-dynamic";

/** Tip triage queue (spec G2 /console/tips, WS4-08). Quarantined tips stay visible in their own tab. */
export default async function TipsQueue({ searchParams }: { searchParams: { tab?: string } }) {
  await requireOfficer("all");
  const tab = parseTipTab(searchParams.tab);
  const sb = consoleServerClient();

  let q = sb.from("tips").select("*, tip_media(media_id, kind), tip_reviews(useful, at)").order("received_week", { ascending: false }).order("tip_id").limit(200);
  const st = statusesFor(tab);
  if (st) q = q.in("status", st);
  const [{ data, error }, { data: appeals }] = await Promise.all([
    q, sb.from("public_incidents").select("public_incident_id, title"),
  ]);
  const tips = (data ?? []) as TipRow[];
  const appealTitle = Object.fromEntries((appeals ?? []).map((a) => [a.public_incident_id, a.title]));

  return (
    <div className="space-y-4">
      <TipsLive />
      <div>
        <h1 className="text-2xl font-bold">Tips</h1>
        <p className="text-sm text-muted">Public tips arrive anonymous and untrusted. The worker screens each one (Tip Guard) before it reaches agents; you decide whether it helps.</p>
      </div>
      <nav className="flex gap-1 border-b border-line" aria-label="Tip status">
        {TIP_TABS.map((t) => (
          <Link key={t} href={`/console/tips?tab=${t}`} aria-current={t === tab ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${t === tab ? "border-signal font-semibold" : "border-transparent text-muted hover:text-ink"}`}>
            {TIP_TAB_LABEL[t]}
          </Link>
        ))}
      </nav>
      {error && <p role="alert" className="text-sm text-red-600">Could not load tips: {error.message}</p>}
      {!error && tips.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">No tips in this tab.</p>
      )}
      <ul className="grid gap-3 lg:grid-cols-2">
        {tips.map((t) => (
          <li key={t.tip_id} className="space-y-2 rounded-xl border border-line bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link href={`/console/tips/${encodeURIComponent(t.tip_id)}`} className="font-mono text-sm font-semibold hover:underline">{t.tip_id}</Link>
              <span className="text-xs text-muted">
                {TIP_CATEGORY_LABEL[t.category] ?? t.category} · week {t.received_week} · {t.status}
                {t.follow_up_enabled ? " · reply possible" : " · fully anonymous"}
                {t.synthetic ? " · synthetic" : ""}
              </span>
            </div>
            <GuardBadges guard={t.guard} status={t.status} />
            {t.public_incident_id && <p className="text-xs">Appeal: <strong>{appealTitle[t.public_incident_id] ?? t.public_incident_id}</strong></p>}
            <UntrustedText text={t.text} clamp />
            <p className="text-xs text-muted">
              {(t.tip_media ?? []).length} file{(t.tip_media ?? []).length === 1 ? "" : "s"}
              {(t.tip_reviews ?? []).length > 0 && ` · reviewed ${(t.tip_reviews ?? []).filter((r) => r.useful).length} useful / ${(t.tip_reviews ?? []).filter((r) => !r.useful).length} not`}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
