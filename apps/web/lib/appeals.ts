/**
 * Public appeal drafts and publishing (spec G1/G2, D3.13, WS4-07). Pure helpers shared by the pages and tests.
 *
 * The leak list mirrors public.appeal_text_leaks (migration 0006_02) and app/agents/sanitiser.py, with one
 * shared fixture (tests/agents/appeal_leaks.json). This copy is for immediate feedback in the form: the
 * database trigger is what actually blocks a leaky publish. Clock times are allowed, because D3.13's own
 * example asks for CCTV "between 7:30 and 8:00 pm".
 */

export const LEAKS: { kind: string; re: RegExp }[] = [
  { kind: "plate", re: /(^|[^A-Za-z0-9])[A-Z]{2} ?[0-9]{1,2} ?[A-Z?]{0,3} ?[0-9]{3,4}([^0-9]|$)/ },
  { kind: "internal id", re: /(^|[^A-Za-z])(CHN|PS)-[A-Z0-9-]+/ },
  { kind: "FIR number", re: /(^|[^0-9])[0-9]{1,5}\/[0-9]{4}([^0-9]|$)/ },
  { kind: "phone or long number", re: /[0-9]{6,}/ },
];

export function leakKind(text: string | null | undefined): string | null {
  const t = text ?? "";
  for (const l of LEAKS) if (l.re.test(t)) return l.kind;
  return null;
}

export type AppealStatus = "draft" | "published" | "withdrawn";

export type Appeal = {
  public_incident_id: string;
  crime_id: string | null;
  title: string;
  category: string;
  area_label: string;
  cell: string;
  week: string;
  time_window: string;
  summary: string;
  looking_for: string[];
  approved_by: string | null;
  sanitiser_model: string | null;
  status: AppealStatus;
  published_at: string | null;
};

export type AppealRequest = {
  request_id: number;
  crime_id: string;
  status: "requested" | "drafted" | "failed";
  public_incident_id: string | null;
  error: string | null;
  requested_at: string;
};

export type AppealEdit = { title: string; summary: string; looking_for: string[] };

/** Parse the form's "one item per line" box: trimmed, empty lines dropped, at most 4 items. */
export function parseLookingFor(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 4);
}

/** Problems that stop a publish (shown in the form; the DB trigger enforces the leak list too). */
export function validateAppeal(e: AppealEdit): string | null {
  if (!e.title.trim()) return "Add a title.";
  if (e.title.length > 90) return "Keep the title under 90 characters.";
  if (!e.summary.trim()) return "Add a summary.";
  if (e.summary.length > 500) return "Keep the summary under 500 characters.";
  for (const [field, text] of [["title", e.title], ["summary", e.summary], ...e.looking_for.map((t) => ["looking for", t])]) {
    const k = leakKind(text);
    if (k) return `The ${field} contains a ${k}. Public appeals must not.`;
  }
  return null;
}

/** Crime ids are plain text ids; never pass anything else into a query filter. */
export function isCrimeId(v: string): boolean {
  return /^[A-Z]{2,4}-[A-Z]{2}-\d{4}-\d{3,8}$/.test(v.trim());
}

export const STATUS_LABEL: Record<AppealStatus, string> = {
  draft: "Draft",
  published: "Published",
  withdrawn: "Withdrawn",
};

/** Tips per appeal (console list). Tips not attached to an appeal are ignored. */
export function tipCounts(rows: { public_incident_id: string | null }[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const r of rows) if (r.public_incident_id) m.set(r.public_incident_id, (m.get(r.public_incident_id) ?? 0) + 1);
  return m;
}
