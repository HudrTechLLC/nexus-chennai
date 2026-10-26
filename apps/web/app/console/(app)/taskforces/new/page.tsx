import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { suggestedName } from "@/lib/taskforces";
import { ProposeForm } from "@/components/console/taskforces/TaskforceForms";

export const dynamic = "force-dynamic";

/**
 * Propose a joint task force (LNK-09). Deep links: ?series_id=SER-… (series detail button) and
 * ?alert_id=LA-… (the worker's joint_case_proposal notification on an approved alert).
 */
export default async function NewTaskforce({ searchParams }: { searchParams: { series_id?: string; alert_id?: string } }) {
  await requireOfficer(["analyst", "supervisor", "admin"]);
  const sb = consoleServerClient();
  const seriesId = searchParams.series_id?.trim() || null;
  const alertId = searchParams.alert_id?.trim() || null;

  const [series, alert] = await Promise.all([
    seriesId ? sb.from("series").select("series_id, name").eq("series_id", seriesId).maybeSingle() : Promise.resolve({ data: null }),
    alertId ? sb.from("link_alerts").select("alert_id, crimes, status").eq("alert_id", alertId).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  const s = series.data as { series_id: string; name: string } | null;
  const a = alert.data as { alert_id: string; crimes: string[]; status: string } | null;
  const missing = (seriesId && !s) || (alertId && !a);
  const sourceLabel = s ? `series ${s.name} (${s.series_id})` : a ? `link alert ${a.alert_id} (${a.crimes.length} cases, ${a.status})` : null;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Link href="/console/taskforces" className="text-sm text-muted hover:text-ink">← Task forces</Link>
      <h1 className="text-2xl font-bold">Propose a joint task force</h1>
      {missing ? (
        <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">
          {seriesId && !s ? `Series ${seriesId} was not found.` : `Alert ${alertId} was not found.`} You can still propose one with case ids below.
        </p>
      ) : null}
      <section className="rounded-xl border border-line bg-surface p-5">
        <ProposeForm defaults={{
          name: suggestedName({ seriesName: s?.name, alertId: a?.alert_id }),
          series_id: s?.series_id ?? null, alert_id: a?.alert_id ?? null, sourceLabel,
        }} />
      </section>
    </div>
  );
}
