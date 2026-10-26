import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { STATUS_LABEL, type Appeal } from "@/lib/appeals";
import { canWriteCase } from "@/lib/cases";
import { parseImages, publicStillUrl, STILL_ALT } from "@/lib/appealStills";
import { AppealEditor } from "@/components/console/appeals/AppealForms";
import { StillsPanel } from "@/components/console/appeals/StillsPanel";

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
  // Mirrors can_write_crime (0002): own station for station officers; supervisor and admin everywhere.
  // RLS enforces it on save; this only decides whether to show the form (an other-station officer sees it read-only).
  const { data: crime } = a.crime_id
    ? await sb.from("crimes_citywide").select("station_id").eq("crime_id", a.crime_id).maybeSingle()
    : { data: null };
  const crimeStation = (crime as { station_id: string } | null)?.station_id ?? null;
  // No linked case: only supervisor and admin may write (can_write_crime needs a station to match).
  const canWrite = crimeStation ? canWriteCase(officer.role, officer.stationId, crimeStation) : officer.role !== "station_officer";
  const stills = parseImages(a.images);
  const readOnlyWhy = canWrite
    ? null
    : crimeStation
      ? `Read-only: this appeal belongs to ${crimeStation.replace(/^PS-/, "")}. Only that station, supervisors and admins can edit it.`
      : "Read-only: this appeal has no linked case, so only supervisors and admins can edit it.";

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
          {readOnlyWhy && <p className="mb-3 rounded-md border border-line bg-bg px-3 py-2 text-xs text-muted">{readOnlyWhy}</p>}
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
            {stills.length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {stills.map((st) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img key={st.path} src={publicStillUrl(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "", st.path)} alt={STILL_ALT}
                       width={st.width} height={st.height} className="aspect-video w-full rounded-md border border-line object-cover" />
                ))}
              </div>
            )}
            <p className="text-xs text-muted">Location is shown only as an area and a hex cell. No case numbers, names, plates or exact times.</p>
          </div>
        </section>
      </div>
      <StillsPanel appealId={a.public_incident_id} crimeId={a.crime_id} images={a.images} status={a.status} canWrite={canWrite} />
    </div>
  );
}
