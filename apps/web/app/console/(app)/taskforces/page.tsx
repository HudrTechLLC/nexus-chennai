import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { officerNames } from "@/lib/alertsData";
import { fetchTaskforces, taskforceCounts } from "@/lib/taskforcesData";
import { canPropose, countByStatus, isTfStatus, STATUS_LABEL, type TfStatus } from "@/lib/taskforces";
import { TfStatusPill } from "@/components/console/taskforces/TfBits";

export const dynamic = "force-dynamic";

const fmt = (iso: string) => new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });

const EMPTY: Record<TfStatus | "all", string> = {
  all: "No joint task forces yet. When linked cases span stations, an analyst proposes one here (or from a series or an approved alert), and a supervisor approves it.",
  proposed: "No proposals are waiting for a supervisor.",
  active: "No active joint task forces. Proposals become active when a supervisor approves them.",
  closed: "No closed task forces yet.",
  declined: "No declined proposals.",
};

export default async function TaskforcesPage({ searchParams }: { searchParams: { status?: string } }) {
  const officer = await requireOfficer("all");
  const tab: TfStatus | "all" = isTfStatus(searchParams.status) ? searchParams.status : "all";
  const sb = consoleServerClient();
  const { rows, error } = await fetchTaskforces(sb);
  const counts = countByStatus(rows);
  const shown = tab === "all" ? rows : rows.filter((r) => r.status === tab);
  const [sizes, names] = await Promise.all([
    taskforceCounts(sb, shown.map((r) => r.taskforce_id)),
    officerNames(sb, shown.map((r) => r.created_by).filter((x): x is string => !!x)),
  ]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Joint task forces</h1>
          <p className="max-w-prose text-sm text-muted">
            Officers from several stations working linked cases together: members, linked cases and notes. Analysts propose, supervisors approve.
          </p>
        </div>
        {canPropose(officer.role) && <Link href="/console/taskforces/new" className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white">Propose task force</Link>}
      </div>

      <nav className="flex gap-1 border-b border-line" aria-label="Task force status">
        {(["all", "proposed", "active", "closed", "declined"] as const).map((t) => (
          <Link key={t} href={t === "all" ? "/console/taskforces" : `/console/taskforces?status=${t}`} aria-current={t === tab ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${t === tab ? "border-signal font-semibold" : "border-transparent text-muted hover:text-ink"}`}>
            {t === "all" ? "All" : STATUS_LABEL[t]} <span className="font-mono text-xs text-muted">{counts[t]}</span>
          </Link>
        ))}
      </nav>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load task forces: {error}</p>}
      {!error && shown.length === 0 && <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">{EMPTY[tab]}</p>}

      <ul className="grid gap-3 md:grid-cols-2">
        {shown.map((t) => (
          <li key={t.taskforce_id}>
            <Link href={`/console/taskforces/${encodeURIComponent(t.taskforce_id)}`} className="block h-full rounded-xl border border-line bg-surface p-4 hover:border-signal">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold leading-tight">{t.name}</h2>
                <TfStatusPill status={t.status} />
              </div>
              <p className="mt-0.5 font-mono text-xs text-muted">{t.taskforce_id}</p>
              {t.purpose && <p className="mt-2 line-clamp-2 text-sm">{t.purpose}</p>}
              <p className="mt-2 text-xs text-muted">
                {sizes[t.taskforce_id]?.members ?? 0} members · {sizes[t.taskforce_id]?.cases ?? 0} linked cases
                {t.series_id && <> · series {t.series_id}</>}
                {" "}· proposed {fmt(t.created_at)}{t.created_by && names[t.created_by] ? ` by ${names[t.created_by]}` : ""}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
