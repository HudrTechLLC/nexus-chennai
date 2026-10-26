import { NextResponse } from "next/server";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { MAPPING_COLUMNS, RUN_COLUMNS, rpcMessage } from "@/lib/onboarding";

export const dynamic = "force-dynamic";

/** GET: the run and its mapping rows, for the onboarding page's poll (WS1-23). Read-only, admin RLS. */
export async function GET(_req: Request, { params }: { params: { runId: string } }) {
  const officer = await getOfficer();
  if (!officer) return NextResponse.json({ ok: false, error: "Sign in again." }, { status: 401 });
  if (officer.role !== "admin") return NextResponse.json({ ok: false, error: "Admins only." }, { status: 403 });
  const runId = decodeURIComponent(params.runId);
  const sb = consoleServerClient();
  const [run, mappings] = await Promise.all([
    sb.from("onboarding_runs").select(RUN_COLUMNS).eq("run_id", runId).maybeSingle(),
    sb.from("onboarding_mappings").select(MAPPING_COLUMNS).eq("run_id", runId).order("source_col"),
  ]);
  const err = run.error ?? mappings.error;
  if (err) return NextResponse.json({ ok: false, error: rpcMessage(err) }, { status: 500 });
  if (!run.data) return NextResponse.json({ ok: false, error: "Run not found." }, { status: 404 });
  return NextResponse.json(
    { ok: true, run: run.data, mappings: mappings.data ?? [] },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}
