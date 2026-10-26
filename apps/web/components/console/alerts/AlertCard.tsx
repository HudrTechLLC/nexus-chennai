import Link from "next/link";
import { coverageCapLine, coverageOf, decisionState, factorRows, latestDecision, pct, REASON_LABEL, type LinkAlert } from "@/lib/alerts";
import { crimeTitle, type CrimeBrief } from "@/lib/alertsData";
import { BandPill, FactorBars, ScoreRing, StatusPill } from "./AlertBits";

function fmt(at: string) {
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Inbox card (spec G2 exhibit "Link alert cards"). */
export function AlertCard({ alert, crimes, deciderNames }: {
  alert: LinkAlert; crimes: Record<string, CrimeBrief>; deciderNames: Record<string, string>;
}) {
  const state = decisionState(alert);
  const last = latestDecision(alert.alert_decisions);
  const rows = factorRows(alert.link_factors);
  const title = alert.crimes.map((id) => crimeTitle(crimes[id], id)).join(" ↔ ");
  const first = crimes[alert.crimes[0]];
  const memDelta = alert.memory_applied?.[0];
  const capLine = coverageCapLine(alert);

  return (
    <article className="min-w-0 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start gap-4">
        <ScoreRing score={alert.score} band={alert.band} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <BandPill band={alert.band} />
            <StatusPill state={state} />
            <span className="font-mono text-xs text-muted">{alert.alert_id} · {alert.kind}</span>
            <span className="font-mono text-xs text-muted">coverage {pct(coverageOf(alert))}</span>
          </div>
          <h2 className="mt-1 truncate text-lg font-bold">
            <Link href={`/console/alerts/${encodeURIComponent(alert.alert_id)}`} className="hover:underline">{title}</Link>
          </h2>
          <p className="text-xs text-muted">
            {first?.sub_type ?? first?.category ?? "—"} · {alert.stations.length} station{alert.stations.length === 1 ? "" : "s"} · raised {fmt(alert.created_at)}
          </p>
        </div>
      </div>

      {capLine && <p className="mt-3 text-xs text-muted">{capLine}</p>}
      <div className="mt-3"><FactorBars rows={rows} compact /></div>
      <p className="mt-3 text-sm">{alert.rationale}</p>

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {alert.skeptic && (
          <span className="rounded-md bg-bg px-2 py-1">
            Skeptic: {alert.skeptic.rounds} round{alert.skeptic.rounds === 1 ? "" : "s"}
            {alert.skeptic.struck.length ? `, struck ${alert.skeptic.struck.join(", ")}` : ""}
          </span>
        )}
        {memDelta && (
          <span className="rounded-md bg-accent-soft px-2 py-1" title={memDelta.text}>
            Memory applied {memDelta.effect}
            {alert.memory_applied.length > 1 ? ` (+${alert.memory_applied.length - 1} more)` : ""}
          </span>
        )}
      </div>

      {state === "rejected" && last && (
        <p className="mt-3 rounded-md border border-line bg-bg px-3 py-2 text-sm">
          <strong>Rejected · {last.reason_code ? REASON_LABEL[last.reason_code] : "no reason"}</strong>
          <span className="text-muted"> ({deciderNames[last.by] ?? "analyst"}, {fmt(last.at)})</span>
          {last.note ? <>: {last.note}</> : null}
        </p>
      )}
    </article>
  );
}
