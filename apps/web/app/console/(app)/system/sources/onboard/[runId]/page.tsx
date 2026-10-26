import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import {
  MAPPING_COLUMNS, RUN_COLUMNS, type OnboardingField, type OnboardingMapping, type OnboardingRun,
} from "@/lib/onboarding";
import { RunView } from "@/components/console/onboarding/RunView";

export const dynamic = "force-dynamic";

/** One onboarding run (WS1-23), admin only: status, proposed mapping, DQ findings and the decision. */
export default async function OnboardRunPage({ params }: { params: { runId: string } }) {
  await requireOfficer("admin");
  const runId = decodeURIComponent(params.runId);
  if (!/^[0-9a-f-]{36}$/i.test(runId)) notFound();
  const sb = consoleServerClient();
  const [run, mappings, fields] = await Promise.all([
    sb.from("onboarding_runs").select(RUN_COLUMNS).eq("run_id", runId).maybeSingle(),
    sb.from("onboarding_mappings").select(MAPPING_COLUMNS).eq("run_id", runId).order("source_col"),
    sb.from("onboarding_fields").select("field, label, required, kind, sort").order("sort"),
  ]);
  if (!run.error && !run.data) notFound();
  const error = run.error ?? mappings.error ?? fields.error;
  const r = run.data as OnboardingRun | null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/console/system/sources/onboard" className="text-sm text-muted underline-offset-2 hover:underline">← Onboard a new source</Link>
        <h1 className="mt-1 text-2xl font-bold">{r?.label ?? "Onboarding run"}</h1>
        {r && (
          <p className="mt-1 text-sm text-muted">
            <span className="font-mono text-xs">{r.source_key}</span> · {r.use_sample ? "sample export" : "uploaded CSV"}
          </p>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-red-600">Could not load the run: {error.message}</p>}
      {r && !error && (
        <RunView initialRun={r} initialMappings={(mappings.data ?? []) as OnboardingMapping[]} fields={(fields.data ?? []) as OnboardingField[]} />
      )}
    </div>
  );
}
