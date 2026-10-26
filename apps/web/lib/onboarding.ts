/**
 * New source onboarding (WS1-23): pure helpers for the console UI. The contract is migration 0007_15
 * (nexus-1): onboarding_runs / onboarding_mappings / onboarding_fields, read under admin RLS, and the
 * admin-only RPCs onboarding_start, onboarding_save_mapping and onboarding_decide. The worker does the
 * profiling, the mapping proposal and the registration; the console never reaches Zetaris (D-019).
 */

// =====================
// Types (column names exactly as in 0007_15)
// =====================

export const ONBOARDING_STATUSES = [
  "uploaded", "profiling", "proposed", "approved", "registering", "registered", "rejected", "failed",
] as const;
export type OnboardingStatus = (typeof ONBOARDING_STATUSES)[number];

export const TRANSFORMS = ["none", "date_dmy", "datetime_dmy_hm", "latlong_lat", "latlong_lon", "trim_upper"] as const;
export type Transform = (typeof TRANSFORMS)[number];

export const TRANSFORM_LABEL: Record<Transform, string> = {
  none: "as is",
  date_dmy: "date, DD-MM-YYYY",
  datetime_dmy_hm: "date and time, DD-MM-YYYY HH:MM",
  latlong_lat: "latitude from \"lat,lon\"",
  latlong_lon: "longitude from \"lat,lon\"",
  trim_upper: "trim and upper-case",
};

export type ProfileColumn = { column: string; type?: string; non_null?: number; distinct?: number; examples?: unknown[] };
export type DqFinding = { rule: string; severity: string; count: number; sample_rows?: unknown[]; detail?: string | null };

export type OnboardingRun = {
  run_id: string;
  source_key: string;
  label: string;
  station_name: string | null;
  use_sample: boolean;
  status: OnboardingStatus;
  error: string | null;
  row_count: number | null;
  profile: ProfileColumn[] | null;
  dq: DqFinding[] | null;
  mapping_source: "model" | "rules" | null;
  trace_run_id: string | null;
  view_name: string | null;
  linking_enabled: boolean;
  reject_reason: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export const RUN_COLUMNS =
  "run_id, source_key, label, station_name, use_sample, status, error, row_count, profile, dq, mapping_source, " +
  "trace_run_id, view_name, linking_enabled, reject_reason, decided_at, created_at, updated_at";

export type OnboardingMapping = {
  source_col: string;
  proposed_field: string | null;
  unified_field: string | null;
  transform: Transform;
  confidence: number | null;
  reason: string | null;
  edited: boolean;
};

export const MAPPING_COLUMNS = "source_col, proposed_field, unified_field, transform, confidence, reason, edited";

export type OnboardingField = { field: string; label: string; required: boolean; kind: string; sort: number };

/** One row the admin changed: what onboarding_save_mapping takes. */
export type MappingEdit = { source_col: string; unified_field: string | null; transform: Transform };

// =====================
// Status
// =====================

export const STATUS_LABEL: Record<OnboardingStatus, string> = {
  uploaded: "Uploaded, waiting for the worker",
  profiling: "Profiling through Zetaris",
  proposed: "Mapping proposed: review it",
  approved: "Approved, waiting to register",
  registering: "Registering the view in Zetaris",
  registered: "Registered, not linked",
  rejected: "Rejected",
  failed: "Failed",
};

/** The happy path, for the stepper. */
export const STEPS: OnboardingStatus[] = ["uploaded", "profiling", "proposed", "approved", "registering", "registered"];

/** Poll while the worker owns the run; stop where a person must act (proposed) and at the end. */
export function shouldPoll(status: OnboardingStatus): boolean {
  return status === "uploaded" || status === "profiling" || status === "approved" || status === "registering";
}

export function isTerminal(status: OnboardingStatus): boolean {
  return status === "registered" || status === "rejected" || status === "failed";
}

export const POLL_MS = 3000;

/** Index of the status on the happy path; rejected/failed sit where the run stopped (proposed or earlier). */
export function stepIndex(status: OnboardingStatus): number {
  const i = STEPS.indexOf(status);
  return i >= 0 ? i : STEPS.indexOf("proposed");
}

// =====================
// Start form
// =====================

export const SOURCE_KEY_RE = /^[a-z0-9_]{3,30}$/;
export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const UPLOAD_MIME = ["text/csv", "application/vnd.ms-excel", "text/plain"];

export type StartInput = { sourceKey: string; label: string; useSample: boolean; file?: { name: string; size: number } | null };

/** Field errors for the start form, checked before anything is uploaded (a stray upload cannot be deleted). */
export function validateStart(input: StartInput): Record<string, string> {
  const e: Record<string, string> = {};
  if (!SOURCE_KEY_RE.test(input.sourceKey)) e.source_key = "3 to 30 characters: lower-case letters, digits and _.";
  const label = input.label.trim();
  if (label.length < 3 || label.length > 80) e.label = "3 to 80 characters.";
  if (!input.useSample) {
    if (!input.file || input.file.size === 0) e.file = "Choose a CSV export, or use the sample export.";
    else if (input.file.size > MAX_UPLOAD_BYTES) e.file = "The file must be 2 MB or smaller.";
    else if (!/\.csv$/i.test(input.file.name)) e.file = "Upload a .csv file.";
  }
  return e;
}

/** A CSV is text: reject bytes that look binary (a NUL in the first 4 KB) before it reaches the bucket. */
export function looksLikeText(bytes: Uint8Array): boolean {
  const n = Math.min(bytes.length, 4096);
  for (let i = 0; i < n; i++) if (bytes[i] === 0) return false;
  return true;
}

export function uploadPath(uuid: string): string {
  return `${uuid}/source.csv`;
}

// =====================
// Mapping
// =====================

export type MappingIssues = { missing: string[]; duplicated: string[] };

/**
 * The same two checks onboarding_decide makes: every required field mapped exactly once. A combined "lat,lon"
 * column maps to lat with transform latlong_lat and the view derives lon from it, so that row also counts as lon.
 */
export function mappingIssues(rows: Pick<OnboardingMapping, "unified_field" | "transform">[], fields: OnboardingField[]): MappingIssues {
  const counts = new Map<string, number>();
  const add = (f: string) => counts.set(f, (counts.get(f) ?? 0) + 1);
  for (const r of rows) {
    if (!r.unified_field) continue;
    add(r.unified_field);
    if (r.unified_field === "lat" && r.transform === "latlong_lat") add("lon");
  }
  const bySort = [...fields].sort((a, b) => a.sort - b.sort);
  return {
    missing: bySort.filter((f) => f.required && !counts.has(f.field)).map((f) => f.field),
    duplicated: bySort.filter((f) => (counts.get(f.field) ?? 0) > 1).map((f) => f.field),
  };
}

/** Only the rows that differ from what is saved (the RPC marks every row it is sent as edited). */
export function mappingEdits(saved: OnboardingMapping[], current: MappingEdit[]): MappingEdit[] {
  const was = new Map(saved.map((m) => [m.source_col, m]));
  return current.filter((c) => {
    const s = was.get(c.source_col);
    return s && ((s.unified_field ?? null) !== (c.unified_field ?? null) || s.transform !== c.transform);
  });
}

export function confidenceLabel(c: number | null): string {
  return c == null ? "—" : `${Math.round(c * 100)}%`;
}

/** Short, single-line text for a profile example or a DQ sample row (raw source values). */
export function clip(value: unknown, max = 60): string {
  const s = typeof value === "string" ? value : JSON.stringify(value);
  const one = (s ?? "").replace(/\s+/g, " ").trim();
  return one.length > max ? `${one.slice(0, max - 1)}…` : one;
}

/** DQ findings by severity, most serious first. */
export function dqCounts(dq: DqFinding[] | null): { severity: string; findings: number; rows: number }[] {
  const order = ["error", "high", "warn", "warning", "medium", "info", "low"];
  const by = new Map<string, { findings: number; rows: number }>();
  for (const f of dq ?? []) {
    const cur = by.get(f.severity) ?? { findings: 0, rows: 0 };
    by.set(f.severity, { findings: cur.findings + 1, rows: cur.rows + (Number(f.count) || 0) });
  }
  const rank = (s: string) => (order.indexOf(s) < 0 ? order.length : order.indexOf(s));
  return Array.from(by.entries()).map(([severity, v]) => ({ severity, ...v })).sort((a, b) => rank(a.severity) - rank(b.severity));
}

/** Friendly text for the RPC errors a person can act on. */
export function rpcMessage(error: { code?: string; message: string }): string {
  if (error.code === "42501") return "Only an admin can do this.";
  if (error.code === "23505") return "A source with this key already exists.";
  if (error.code === "42P01" || /onboarding_\w+.*does not exist|schema cache/i.test(error.message)) {
    return "Source onboarding is not set up in this database yet.";
  }
  return error.message;
}

/** True when the onboarding tables are not there yet (migration not applied): pages hide the section. */
export function isMissingTable(error: { code?: string; message: string } | null | undefined): boolean {
  return !!error && (error.code === "42P01" || error.code === "PGRST205" || /does not exist|schema cache/i.test(error.message));
}
