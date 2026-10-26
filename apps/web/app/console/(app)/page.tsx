import { requireOfficer } from "@/lib/auth";
import { ConsoleNotYet } from "@/components/console/ConsoleFrame";
import { ROLE_LABEL, canDecideAlerts } from "@/lib/roles";

export default async function Overview({ searchParams }: { searchParams: { denied?: string } }) {
  const officer = await requireOfficer();
  return (
    <div className="space-y-4">
      {searchParams.denied && (
        <p className="rounded-md border border-accent bg-accent-soft px-3 py-2 text-sm">
          Your role ({ROLE_LABEL[officer.role]}) cannot open that screen.
        </p>
      )}
      <h1 className="text-2xl font-bold">Command overview</h1>
      <p className="text-sm text-muted">
        Signed in as {officer.name} · {ROLE_LABEL[officer.role]}
        {officer.stationId ? ` · ${officer.stationId}` : " · all stations"} ·{" "}
        {canDecideAlerts(officer.role) ? "can approve or reject link alerts" : "can read link alerts, including rejected ones"}
      </p>
      <ConsoleNotYet
        title="KPIs, alert funnel and briefing"
        task="WS3-04"
        what="Open cases, new link alerts, cross-station links and the raised → Skeptic → analyst funnel. They read from the core tables once those land."
      />
    </div>
  );
}
