import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { isMissingTable, STATUS_LABEL, type OnboardingStatus } from "@/lib/onboarding";
import { StartForm } from "@/components/console/onboarding/StartForm";

export const dynamic = "force-dynamic";

type Row = { run_id: string; source_key: string; label: string; status: OnboardingStatus; row_count: number | null; created_at: string };

const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });

/**
 * New source onboarding (WS1-23), admin only: start a run (upload or the sample export) and see earlier runs.
 * The worker profiles the export through Zetaris and proposes a mapping; an admin reviews and approves it.
 */
export default async function OnboardPage() {
  await requireOfficer("admin");
  const sb = consoleServerClient();
  const runs = await sb.from("onboarding_runs").select("run_id, source_key, label, status, row_count, created_at")
    .order("created_at", { ascending: false }).limit(50);
  const missing = isMissingTable(runs.error);
  const rows = (runs.data ?? []) as Row[];

  return (
    <div className="space-y-6">
      <div>
        <Link href="/console/system/sources" className="text-sm text-muted underline-offset-2 hover:underline">← Data sources</Link>
        <h1 className="mt-1 text-2xl font-bold">Onboard a new source</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Bring in a new station&apos;s export. The worker reads it through Zetaris, profiles every column, proposes how each
          maps to the unified crime fields and runs data-quality checks. You review the mapping and approve or reject it.
          An approved source is registered as its own Zetaris view and is <strong>not linked</strong>: it stays out of the
          unified view and the agents&apos; linking until that is reviewed separately.
        </p>
      </div>

      {missing ? (
        <p role="status" className="rounded-xl border border-line bg-surface p-5 text-sm text-muted">
          Source onboarding is not set up in this database yet (migration 0007_15).
        </p>
      ) : (
        <>
          <StartForm />
          {runs.error && <p role="alert" className="text-sm text-red-600">Could not load runs: {runs.error.message}</p>}
          <section aria-labelledby="ob-runs" className="rounded-xl border border-line bg-surface p-5">
            <h2 id="ob-runs" className="font-semibold">Onboarding runs</h2>
            {rows.length === 0 ? (
              <p className="mt-1 text-sm text-muted">None yet.</p>
            ) : (
              <ul className="mt-2 divide-y divide-line text-sm">
                {rows.map((r) => (
                  <li key={r.run_id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2">
                    <Link href={`/console/system/sources/onboard/${encodeURIComponent(r.run_id)}`} className="font-medium text-signal underline-offset-2 hover:underline">{r.label}</Link>
                    <span className="font-mono text-xs text-muted">{r.source_key}</span>
                    <span className="text-xs">{STATUS_LABEL[r.status] ?? r.status}</span>
                    {r.row_count != null && <span className="text-xs text-muted">{r.row_count.toLocaleString("en-IN")} rows</span>}
                    <span className="text-xs text-muted">{when(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
