/**
 * Read-only copy of the F2 scoring defaults (services/api/app/scoring/weights.py), for /console/admin.
 * The Python file is the source of truth; lib/__tests__/weights.test.ts fails if this copy drifts.
 * There is no edit path: weights change only with a recorded decision (rule R12).
 */

export const WEIGHTS_VERSION = "f2-default-v1";

export const FACTOR_LABELS: Record<string, string> = {
  mo_similarity: "MO similarity",
  space_time: "Space–time",
  vehicle: "Vehicle / ANPR",
  suspect_description: "Suspect description",
  weapon_tool: "Weapon / tool",
  target_profile: "Target profile",
  forensic: "Forensic match",
  corroboration: "Corroboration (tips, 112, news)",
  offender_return: "Offender return",
};

/** Order follows the F2 table, as in weights.py. */
export const DEFAULT_WEIGHTS: Record<string, number> = {
  mo_similarity: 0.25,
  space_time: 0.15,
  vehicle: 0.15,
  suspect_description: 0.12,
  weapon_tool: 0.08,
  target_profile: 0.05,
  forensic: 0.08,
  corroboration: 0.07,
  offender_return: 0.05,
};

export const SCORING_RULES = {
  BAND_HIGH: 0.75,
  BAND_MEDIUM: 0.55,
  FORENSIC_FLOOR: 0.8,
  HMEM_CAP: 0.08,
  MIN_COVERAGE_FOR_HIGH: 0.5,
  MIN_FACTORS_FOR_ALERT: 2,
} as const;

export type FactorRow = { factor: string; weight: number | null; alert_id: string; created_at: string | null };

export type FactorUsage = {
  factor: string;
  label: string;
  defaultWeight: number;
  /** Each distinct weight persisted alerts were scored with, with its alert count and date range. */
  used: { weight: number; alerts: number; first: string | null; last: string | null; isDefault: boolean }[];
};

const close = (a: number, b: number) => Math.abs(a - b) < 1e-6; // link_factors.weight is a float4

/**
 * Weights that persisted alerts were actually scored with, per factor. A factor with no rows means
 * no persisted alert had data for it (link_factors stores only factors with data), not a weight of 0.
 */
export function factorUsage(rows: FactorRow[]): FactorUsage[] {
  const byFactor = new Map<string, Map<number, { alerts: Set<string>; first: string | null; last: string | null }>>();
  for (const r of rows) {
    if (r.weight == null) continue;
    const w = Math.round(r.weight * 1e4) / 1e4;
    const m = byFactor.get(r.factor) ?? new Map();
    const e = m.get(w) ?? { alerts: new Set<string>(), first: null, last: null };
    e.alerts.add(r.alert_id);
    if (r.created_at) {
      if (!e.first || r.created_at < e.first) e.first = r.created_at;
      if (!e.last || r.created_at > e.last) e.last = r.created_at;
    }
    m.set(w, e);
    byFactor.set(r.factor, m);
  }
  const known = Object.keys(DEFAULT_WEIGHTS);
  const extra = Array.from(byFactor.keys()).filter((f) => !known.includes(f)).sort();
  return [...known, ...extra].map((factor) => {
    const def = DEFAULT_WEIGHTS[factor] ?? NaN;
    const used = Array.from(byFactor.get(factor)?.entries() ?? [])
      .map(([weight, e]) => ({ weight, alerts: e.alerts.size, first: e.first, last: e.last, isDefault: close(weight, def) }))
      .sort((a, b) => b.alerts - a.alerts);
    return { factor, label: FACTOR_LABELS[factor] ?? factor, defaultWeight: def, used };
  });
}

/** Alerts that had at least one factor scored with a non-default weight (a "custom" scoring run). */
export function nonDefaultAlerts(rows: FactorRow[]): string[] {
  const out = new Set<string>();
  for (const r of rows) {
    const def = DEFAULT_WEIGHTS[r.factor];
    if (r.weight != null && (def === undefined || !close(r.weight, def))) out.add(r.alert_id);
  }
  return Array.from(out).sort();
}

/** Alerts per recorded weights version; alerts written before 0007_07 have none ("pre-versioning"). */
export function versionCounts(alerts: { weights_version: string | null }[]): { version: string; alerts: number; current: boolean }[] {
  const m = new Map<string, number>();
  for (const a of alerts) {
    const v = a.weights_version?.trim() || "pre-versioning";
    m.set(v, (m.get(v) ?? 0) + 1);
  }
  return Array.from(m.entries())
    .map(([version, n]) => ({ version, alerts: n, current: version === WEIGHTS_VERSION }))
    .sort((a, b) => b.alerts - a.alerts || a.version.localeCompare(b.version));
}
