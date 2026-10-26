import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { DEFAULT_WEIGHTS, SCORING_RULES, WEIGHTS_VERSION, factorUsage, nonDefaultAlerts, versionCounts, type FactorRow } from "@/lib/weights";

export const dynamic = "force-dynamic";

/** PostgREST returns at most this many rows per request; say so instead of showing a silently cut list. */
const ROW_CAP = 1000;

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata" }) : "—");
const pct = (n: number) => n.toFixed(2);

type Profile = { user_id: string; name: string | null; role: string; station_id: string | null };
type Station = { station_id: string; name: string; type: string | null; zone: string | null; district: string | null };

/**
 * Admin (spec G2 `/console/admin`, WS3-14): users, stations and scoring weights, all READ-ONLY.
 * Weights cannot be edited here: they change only with a recorded decision (rule R12).
 */
export default async function AdminPage() {
  await requireOfficer("admin");
  const sb = consoleServerClient();
  const [profiles, stations, factors, alerts] = await Promise.all([
    sb.from("profiles").select("user_id, name, role, station_id").order("role").order("name"),
    sb.from("stations").select("station_id, name, type, zone, district").order("zone").order("name"),
    sb.from("link_factors").select("alert_id, factor, weight").limit(ROW_CAP),
    sb.from("link_alerts").select("alert_id, created_at, weights_version").limit(ROW_CAP),
  ]);
  const users = (profiles.data ?? []) as Profile[];
  const stationRows = (stations.data ?? []) as Station[];
  const alertRows = (alerts.data ?? []) as { alert_id: string; created_at: string | null; weights_version: string | null }[];
  const alertAt = new Map(alertRows.map((a) => [a.alert_id, a.created_at]));
  const versions = versionCounts(alertRows);
  const rows: FactorRow[] = ((factors.data ?? []) as Omit<FactorRow, "created_at">[]).map((f) => ({ ...f, created_at: alertAt.get(f.alert_id) ?? null }));
  const usage = factorUsage(rows);
  const custom = nonDefaultAlerts(rows);
  const officersAt = new Map<string, number>();
  for (const u of users) if (u.station_id) officersAt.set(u.station_id, (officersAt.get(u.station_id) ?? 0) + 1);
  const stationName = new Map(stationRows.map((s) => [s.station_id, s.name]));
  const capped = (factors.data?.length ?? 0) >= ROW_CAP || (alerts.data?.length ?? 0) >= ROW_CAP;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Admin</h1>
        <p className="text-sm text-muted">
          Users, stations and scoring weights. Read-only: accounts are created in Supabase Auth, and the scoring weights change
          only with a recorded decision (rule R12), so there is no edit button here.
        </p>
      </div>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-1 font-semibold">Scoring weights</h2>
        <p className="mb-3 text-sm text-muted">
          Current version <span className="font-mono text-xs">{WEIGHTS_VERSION}</span>, from the scoring code (spec F2). Bands: high ≥{" "}
          {pct(SCORING_RULES.BAND_HIGH)}, medium ≥ {pct(SCORING_RULES.BAND_MEDIUM)}, below that no alert. A forensic match sets a floor of{" "}
          {pct(SCORING_RULES.FORENSIC_FLOOR)}. Memory adjusts a pair by at most ±{pct(SCORING_RULES.HMEM_CAP)}. Below{" "}
          {pct(SCORING_RULES.MIN_COVERAGE_FOR_HIGH)} evidence coverage the band is capped at medium, and fewer than{" "}
          {SCORING_RULES.MIN_FACTORS_FOR_ALERT} factors with data raise no alert.
        </p>
        <h3 className="mb-1 text-sm font-semibold">Versions recorded on stored alerts</h3>
        <ul className="mb-3 flex flex-wrap gap-2 text-xs">
          {versions.length === 0 && <li className="text-muted">No stored alerts yet.</li>}
          {versions.map((v) => (
            <li key={v.version} className="rounded-full border border-line px-2 py-0.5">
              <span className="font-mono">{v.version}</span>
              {v.current ? " (current)" : ""} · {v.alerts} alert{v.alerts === 1 ? "" : "s"}
            </li>
          ))}
        </ul>
        <h3 className="mb-1 text-sm font-semibold">Weights used by stored alerts</h3>
        <p className="mb-2 text-xs text-muted">
          The weight each stored alert was actually scored with, per factor. Only factors that had data are stored, so a factor with no
          alerts here was not missing a weight: no stored alert had data for it. Alerts scored before version names were recorded show as
          pre-versioning above; for those, the weights themselves are the record, checked here against the current defaults.
        </p>
        {(factors.error || alerts.error) && (
          <p role="alert" className="text-sm text-red-600">Could not load stored alerts: {(factors.error ?? alerts.error)?.message}</p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Factor</th><th>Default</th><th>Used by stored alerts</th></tr>
            </thead>
            <tbody>
              {usage.map((f) => (
                <tr key={f.factor} className="border-t border-line align-top">
                  <td className="py-1.5">{f.label}</td>
                  <td className="font-mono text-xs">{Number.isNaN(f.defaultWeight) ? "— (not in defaults)" : pct(f.defaultWeight)}</td>
                  <td className="text-xs">
                    {f.used.length === 0 && <span className="text-muted">no stored alert had data for this factor</span>}
                    {f.used.map((u) => (
                      <div key={u.weight}>
                        <span className="font-mono">{pct(u.weight)}</span> {u.isDefault ? "✓ default" : <strong className="text-red-600">not the default</strong>} ·{" "}
                        {u.alerts} alert{u.alerts === 1 ? "" : "s"} · {day(u.first)}
                        {u.last && u.last.slice(0, 10) !== u.first?.slice(0, 10) ? ` – ${day(u.last)}` : ""}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          Default weights sum to {pct(Object.values(DEFAULT_WEIGHTS).reduce((a, b) => a + b, 0))}.{" "}
          {custom.length === 0
            ? "Every stored alert was scored with the default weights."
            : `${custom.length} stored alert(s) used non-default weights: ${custom.join(", ")}.`}
          {capped && " Showing the first 1,000 stored rows only."}
        </p>
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Users ({users.length})</h2>
        {profiles.error && <p role="alert" className="text-sm text-red-600">Could not load users: {profiles.error.message}</p>}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Name</th><th>Role</th><th>Station</th></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-line">
                  <td className="py-1.5">{u.name ?? "—"}</td>
                  <td>{u.role.replace("_", " ")}</td>
                  <td className="text-xs">{u.station_id ? `${stationName.get(u.station_id) ?? u.station_id}` : "all stations"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Stations ({stationRows.length})</h2>
        {stations.error && <p role="alert" className="text-sm text-red-600">Could not load stations: {stations.error.message}</p>}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Station</th><th>Id</th><th>Type</th><th>Zone</th><th>District</th><th>Console users</th></tr>
            </thead>
            <tbody>
              {stationRows.map((s) => (
                <tr key={s.station_id} className="border-t border-line">
                  <td className="py-1.5">{s.name}</td>
                  <td className="font-mono text-xs">{s.station_id}</td>
                  <td className="text-xs">{s.type ?? "—"}</td>
                  <td className="text-xs">{s.zone ?? "—"}</td>
                  <td className="text-xs">{s.district ?? "—"}</td>
                  <td className="text-xs">{officersAt.get(s.station_id) ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
