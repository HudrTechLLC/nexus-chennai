/**
 * Linking evaluation report (spec LNK-10, F3; WS2-14): precision / recall of the agents against
 * the planted series, next to the rules-only baseline. The report is produced offline by
 * `python -m app.eval` (services/api/app/eval) and committed as output_examples/eval_report.json;
 * this file only reads it. Unknown shapes parse to null, so the page says "not committed yet"
 * instead of showing invented numbers.
 */

export type PairMetrics = {
  tp: number; fp: number; fn: number;
  precision: number | null; recall: number | null; f1: number | null;
  alerts: number; false_alerts_per_100_cases: number | null;
};
export type BandRow = { band: string; alerts: number; precision: number | null; tp: number; fp: number };
export type TypeRow = { type: string; tp: number; fp: number; fn: number; precision: number | null; recall: number | null; f1: number | null };
export type ModeRow = { mode: string; precision: number | null; recall: number | null; tp: number | null; fp: number | null; fn: number | null; alerts: number | null };

export type EvalReport = {
  agent: PairMetrics & { skeptic_strikes: number | null; series: { predicted_series: number | null; mean_purity: number | null } | null };
  baseline: PairMetrics & { rule: string | null };
  beats: { precision: boolean | null; recall: boolean | null };
  bands: BandRow[];
  types: TypeRow[];
  modes: ModeRow[];
  moCosine: string | null;
  duplicates: { truth_pairs: number; flagged_by_agent: number; flagged_by_baseline: number } | null;
  medianSecondsPerCase: number | null;
  bandText: Record<string, string>;
  provenance: {
    synthetic: boolean | null; sampleMode: boolean | null; hmem: string | null; weightsVersion: string | null;
    method: string | null; casesEvaluated: number | null; truthPositivePairs: number | null;
    withLiveModelFeatures: number | null; withoutFeatures: string[]; featuresWithoutReceipt: string[];
    excludedNonGenerated: number; runId: string | null; logFile: string | null; truthDir: string | null;
  };
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const int = (v: unknown): number => num(v) ?? 0;
const str = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const bool = (v: unknown): boolean | null => (typeof v === "boolean" ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
const entries = (v: unknown): [string, Obj][] =>
  isObj(v) ? Object.entries(v).filter((e): e is [string, Obj] => isObj(e[1])) : [];

function metrics(o: Obj): PairMetrics {
  return {
    tp: int(o.tp), fp: int(o.fp), fn: int(o.fn),
    precision: num(o.precision), recall: num(o.recall), f1: num(o.f1),
    alerts: int(o.alerts), false_alerts_per_100_cases: num(o.false_alerts_per_100_cases),
  };
}

/** Parses the JSON written by app.eval. Returns null for the placeholder or any shape it does not know. */
export function parseEvalReport(raw: unknown): EvalReport | null {
  if (!isObj(raw) || !isObj(raw.agent) || !isObj(raw.baseline_rules_only)) return null;
  const a = raw.agent;
  const b = raw.baseline_rules_only;
  if (num(a.tp) === null || num(b.tp) === null) return null;
  const beats = isObj(raw.beats_baseline) ? raw.beats_baseline : {};
  const d = isObj(raw.duplicates) ? raw.duplicates : null;
  const f = isObj(raw.features) ? raw.features : {};
  const wv = raw.weights_version;
  return {
    agent: {
      ...metrics(a),
      skeptic_strikes: num(a.skeptic_strikes),
      series: isObj(a.series) ? { predicted_series: num(a.series.predicted_series), mean_purity: num(a.series.mean_purity) } : null,
    },
    baseline: { ...metrics(b), rule: str(b.rule) },
    beats: { precision: bool(beats.precision), recall: bool(beats.recall) },
    bands: entries(a.by_band).map(([band, m]) => ({ band, alerts: int(m.alerts), precision: num(m.precision), tp: int(m.tp), fp: int(m.fp) })),
    types: entries(a.by_crime_type)
      .map(([type, m]) => ({ type, tp: int(m.tp), fp: int(m.fp), fn: int(m.fn), precision: num(m.precision), recall: num(m.recall), f1: num(m.f1) }))
      .sort((x, y) => y.tp + y.fp - (x.tp + x.fp) || x.type.localeCompare(y.type)),
    modes: entries(raw.mo_cosine_trial).map(([mode, m]) => ({
      mode, precision: num(m.precision), recall: num(m.recall), tp: num(m.tp), fp: num(m.fp), fn: num(m.fn), alerts: num(m.alerts),
    })),
    moCosine: str(raw.mo_cosine),
    duplicates: d ? { truth_pairs: int(d.truth_pairs), flagged_by_agent: int(d.flagged_by_agent), flagged_by_baseline: int(d.flagged_by_baseline) } : null,
    medianSecondsPerCase: isObj(raw.timing) ? num(raw.timing.median_seconds_per_case) : null,
    bandText: Object.fromEntries(
      isObj(raw.band_accuracy_text) ? Object.entries(raw.band_accuracy_text).filter((e): e is [string, string] => typeof e[1] === "string") : [],
    ),
    provenance: {
      synthetic: bool(raw.synthetic), sampleMode: bool(raw.sample_mode), hmem: str(raw.hmem),
      weightsVersion: str(wv) ?? (num(wv) !== null ? String(wv) : null),
      method: str(raw.method), casesEvaluated: num(raw.cases_evaluated), truthPositivePairs: num(raw.truth_positive_pairs),
      withLiveModelFeatures: num(f.with_live_model_features), withoutFeatures: strs(f.without_features),
      featuresWithoutReceipt: strs(f.features_without_receipt), excludedNonGenerated: strs(raw.excluded_non_generated).length,
      runId: str(raw.run_id), logFile: str(raw.log_file), truthDir: str(raw.truth_dir),
    },
  };
}

/** 0.8333 → "83.3%"; null → "—". */
export function pctOrDash(v: number | null): string {
  return v === null ? "—" : `${(Math.round(v * 1000) / 10).toFixed(1)}%`;
}

/** Agent minus baseline in percentage points, e.g. "+12.5 pts"; null when either side is missing. */
export function deltaPts(agent: number | null, base: number | null): string | null {
  if (agent === null || base === null) return null;
  const d = Math.round((agent - base) * 1000) / 10;
  return `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d).toFixed(1)} pts`;
}

/** Plain-words verdict for one metric, honest when the agents do NOT beat the baseline. */
export function beatsText(metric: "precision" | "recall", beats: boolean | null): string {
  if (beats === null) return `${metric}: not comparable (one side has no value)`;
  return beats ? `${metric}: agents beat the rules-only baseline` : `${metric}: agents do not beat the rules-only baseline`;
}

export const NO_REPORT =
  "No evaluation report committed yet (WS2-14, nexus-2). It appears here after output_examples/eval_report.json lands on main.";
