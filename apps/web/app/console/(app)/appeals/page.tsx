import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { allows } from "@/lib/roles";
import { consoleServerClient } from "@/lib/supabase/server";
import { STATUS_LABEL, tipCounts, type Appeal, type AppealRequest } from "@/lib/appeals";
import { RequestDraftForm } from "@/components/console/appeals/AppealForms";

export const dynamic = "force-dynamic";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "—");
/** PostgREST returns at most 1,000 rows; at the cap, counts are shown as a lower bound. */
const TIP_CAP = 1000;
const TONE = { draft: "border-accent text-accent", published: "border-signal text-signal", withdrawn: "border-line text-muted" } as const;

/** Public appeals (spec G2 / WS4-07): Sanitiser drafts, officer approval, publish to the public site. */
export default async function AppealsPage() {
  const officer = await requireOfficer(["station_officer", "supervisor", "admin"]);
  const sb = consoleServerClient();
  const [appeals, requests] = await Promise.all([
    sb.from("public_incidents")
      .select("public_incident_id, crime_id, title, category, area_label, week, time_window, status, published_at, approved_by")
      .order("week", { ascending: false }).limit(100),
    sb.from("appeal_requests").select("request_id, crime_id, status, public_incident_id, error, requested_at")
      .order("requested_at", { ascending: false }).limit(20),
  ]);
  const rows = (appeals.data ?? []) as Appeal[];
  const ids = rows.map((a) => a.public_incident_id);
  const tipRows = ids.length
    ? (await sb.from("tips").select("public_incident_id").in("public_incident_id", ids).limit(TIP_CAP)).data ?? []
    : [];
  const tips = tipCounts(tipRows as { public_incident_id: string | null }[]);
  const tipsCapped = tipRows.length >= TIP_CAP;
  const reqs = (requests.data ?? []) as AppealRequest[];
  const canWrite = allows(officer.role, ["station_officer", "supervisor", "admin"]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Public appeals</h1>
        <p className="text-sm text-muted">
          The Sanitiser drafts a public appeal from a case without names, plates, exact places or times. You edit it,
          approve it and publish it. Only published appeals appear on the public site, and you can withdraw them at any time.
        </p>
      </div>

      {canWrite && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">Request a draft</h2>
          <RequestDraftForm />
          {reqs.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {reqs.map((r) => (
                <li key={r.request_id} className="flex flex-wrap gap-x-3">
                  <span className="font-mono text-xs">{r.crime_id}</span>
                  <span className={r.status === "failed" ? "text-red-600" : "text-muted"}>{r.status}</span>
                  {r.public_incident_id && (
                    <Link href={`/console/appeals/${encodeURIComponent(r.public_incident_id)}`} className="underline-offset-2 hover:underline">open draft</Link>
                  )}
                  {r.error && <span className="text-xs text-red-600">{r.error}</span>}
                  <span className="text-xs text-muted">{when(r.requested_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Appeals</h2>
        {appeals.error && <p role="alert" className="text-sm text-red-600">Could not load appeals: {appeals.error.message}</p>}
        {!appeals.error && rows.length === 0 && <p className="text-sm text-muted">No appeals yet.</p>}
        <ul className="divide-y divide-line">
          {rows.map((a) => (
            <li key={a.public_incident_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <Link href={`/console/appeals/${encodeURIComponent(a.public_incident_id)}`} className="font-medium underline-offset-2 hover:underline">
                  {a.title}
                </Link>
                <div className="text-xs text-muted">
                  {a.area_label} · {a.week} · {a.time_window}
                  {a.crime_id && <> · case <span className="font-mono">{a.crime_id}</span></>}
                  {a.published_at && <> · published {when(a.published_at)} by {a.approved_by}</>}
                </div>
              </div>
              <span className="flex items-center gap-2">
                <span className="text-xs text-muted">
                  {tips.get(a.public_incident_id) ?? 0}{tipsCapped ? "+" : ""} tip{(tips.get(a.public_incident_id) ?? 0) === 1 ? "" : "s"}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-xs ${TONE[a.status]}`}>{STATUS_LABEL[a.status]}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
