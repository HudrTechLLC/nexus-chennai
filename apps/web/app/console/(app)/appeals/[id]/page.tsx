import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { STATUS_LABEL, type Appeal } from "@/lib/appeals";
import { AppealEditor } from "@/components/console/appeals/AppealForms";

export const dynamic = "force-dynamic";

/** One appeal: what the public will see, with edit → approve and publish, or withdraw. */
export default async function AppealPage({ params }: { params: { id: string } }) {
  const officer = await requireOfficer(["station_officer", "supervisor", "admin"]);
  const id = decodeURIComponent(params.id);
  if (!/^PI-[A-Za-z0-9-]{1,40}$/.test(id)) notFound();
  const sb = consoleServerClient();
  const { data } = await sb.from("public_incidents").select("*").eq("public_incident_id", id).maybeSingle();
  if (!data) notFound();
  const a = data as Appeal;
  // can_write_crime (0002): own station for station officers; supervisor and admin everywhere. RLS enforces it.
  const canWrite = officer.role !== "station_officer" || (!!a.crime_id && !!officer.stationId);

  return (
    <div className="space-y-5">
      <div>
        <Link href="/console/appeals" className="text-sm text-muted hover:text-ink">← Appeals</Link>
        <h1 className="mt-1 text-2xl font-bold">{a.title}</h1>
        <p className="text-sm text-muted">
          {STATUS_LABEL[a.status]} · {a.area_label} · {a.week} · {a.time_window} · cell <span className="font-mono text-xs">{a.cell}</span>
          {a.sanitiser_model && <> · drafted by <span className="font-mono text-xs">{a.sanitiser_model}</span></>}
          {a.approved_by && <> · approved by {a.approved_by}</>}
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">Edit</h2>
          <AppealEditor appeal={a} canWrite={canWrite} />
        </section>
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">What the public sees</h2>
          <div className="space-y-2 text-sm">
            <div className="text-xs uppercase tracking-wider text-muted">{a.category} · {a.area_label} · {a.time_window}</div>
            <div className="text-lg font-semibold">{a.title}</div>
            <p>{a.summary}</p>
            {a.looking_for.length > 0 && (
              <ul className="list-disc pl-5">{a.looking_for.map((l, i) => <li key={i}>{l}</li>)}</ul>
            )}
            <p className="text-xs text-muted">Location is shown only as an area and a hex cell. No case numbers, names, plates or exact times.</p>
          </div>
        </section>
      </div>
    </div>
  );
}
