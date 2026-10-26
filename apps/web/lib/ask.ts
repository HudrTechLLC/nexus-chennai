/**
 * Ask Nexus (WS3-30): a plain-English question becomes a plan of Zetaris queries, run by the worker.
 * Transport is a table plus polling (Vercel cannot reach Zetaris): the console inserts a row in
 * ask_questions, the worker plans and answers, and the console polls the row until it settles.
 * Contract v1 from nexus-5 (0007_15_ask_questions.sql); the shapes below copy it exactly.
 */

// =====================
// Types (ask_questions row, contract v1)
// =====================

export type AskStatus = "queued" | "planning" | "running" | "answered" | "unmappable" | "failed";

export type AskStep = { query: string; params?: Record<string, unknown>; purpose: string; query_id?: string | null; rows?: number | null };
export type AskFilter = { field: string; op: string; value: unknown; label: string };
export type AskPlan = { steps: AskStep[]; filters: AskFilter[]; understood: string; notes?: string[]; model_plan?: unknown };
export type AskAnswerRow = { crime_id: string; why: string };
export type AskAnswer = { summary: string; total: number; truncated: boolean; rows: AskAnswerRow[]; excluded_test_filings?: number };

export type AskQuestion = {
  question_id: string;
  asked_by: string;
  question: string;
  status: AskStatus;
  created_at: string;
  started_at: string | null;
  answered_at: string | null;
  run_id: string | null;
  model: string | null;
  routed_model: string | null;
  receipt_id: string | null;
  error: string | null;
  plan: AskPlan | null;
  answer: AskAnswer | null;
};

/** What the console reads for each answer row, under crimes RLS (can_read_crime). */
export type AskCrime = {
  crime_id: string; category: string | null; sub_type: string | null; station_id: string | null;
  occurred_from: string | null; address: string | null; lat: number | null; lon: number | null; status: string | null;
};

export const ASK_CRIME_COLUMNS = "crime_id, category, sub_type, station_id, occurred_from, address, lat, lon, status";

// =====================
// Question + polling
// =====================

export const QUESTION_MIN = 3;
export const QUESTION_MAX = 300;
export const POLL_MS = 2000;
export const POLL_GIVE_UP_MS = 120_000;
export const RECENT_LIMIT = 5;

export const SAMPLE_QUESTIONS = [
  "Chain snatchings on a red Pulsar in the last 90 days",
  "Chain snatchings in Adyar after 7 pm in the last 90 days",
  "Robberies in Velachery that are still undetected since 1 September",
] as const;

/** The trimmed question, or the reason it cannot be sent. */
export function checkQuestion(raw: string): { ok: true; question: string } | { ok: false; reason: string } {
  const q = raw.replace(/\s+/g, " ").trim();
  if (q.length < QUESTION_MIN) return { ok: false, reason: "Type a question first." };
  if (q.length > QUESTION_MAX) return { ok: false, reason: `Keep it under ${QUESTION_MAX} characters.` };
  return { ok: true, question: q };
}

export const isSettled = (s: AskStatus) => s === "answered" || s === "unmappable" || s === "failed";

export const STATUS_TEXT: Record<AskStatus, string> = {
  queued: "Waiting for the worker…",
  planning: "Planning the search…",
  running: "Running the Zetaris queries…",
  answered: "Answered",
  unmappable: "Can't answer that",
  failed: "Something went wrong",
};

/** Poll again? Stop when the row has settled, or give up after POLL_GIVE_UP_MS (the worker may still finish). */
export function nextPoll(status: AskStatus, elapsedMs: number): "poll" | "done" | "gave_up" {
  if (isSettled(status)) return "done";
  return elapsedMs >= POLL_GIVE_UP_MS ? "gave_up" : "poll";
}

// =====================
// Results under RLS
// =====================

export type AskResultRow = AskCrime & { why: string };

/**
 * Join the answer rows (in the answer's order, newest first) with the crimes this officer may read.
 * An id the crimes read did not return is never shown: it only counts towards `hidden`.
 */
export function visibleResults(answerRows: AskAnswerRow[], readable: AskCrime[]): { rows: AskResultRow[]; hidden: number } {
  const byId = new Map(readable.map((c) => [c.crime_id, c]));
  const rows: AskResultRow[] = [];
  let hidden = 0;
  const seen = new Set<string>();
  for (const a of answerRows) {
    if (seen.has(a.crime_id)) continue;
    seen.add(a.crime_id);
    const c = byId.get(a.crime_id);
    if (c) rows.push({ ...c, why: a.why });
    else hidden += 1;
  }
  return { rows, hidden };
}

/** Map points for the hits: rows with coordinates, labelled for the map's hover. */
export function hitScenes(rows: AskResultRow[]): { id: string; p: [number, number]; exact: boolean; at: string | null; week: null; label: string }[] {
  return rows
    .filter((r) => typeof r.lat === "number" && typeof r.lon === "number")
    .map((r) => ({ id: r.crime_id, p: [r.lon as number, r.lat as number], exact: true, at: r.occurred_from, week: null, label: r.crime_id }));
}

/** "Chain snatching" from category "robbery" + sub_type "chain_snatching"; falls back to the category. */
export function crimeLabel(c: Pick<AskCrime, "category" | "sub_type">): string {
  const words = (s: string) => s.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());
  if (c.sub_type) return words(c.sub_type);
  return c.category ? words(c.category) : "Crime";
}

/**
 * What to tell the officer when the insert is refused. The "3 questions waiting" check_violation is
 * written for officers, so it is shown as is; a missing table means the feature is not on here yet.
 */
export function insertErrorText(err: { code?: string; message?: string } | null): string {
  const msg = err?.message ?? "";
  if (err?.code === "23514" || /questions waiting/i.test(msg)) return msg;
  if (err?.code === "42P01" || /ask_questions.*(does not exist|schema cache)|relation .*ask_questions/i.test(msg)) return "Ask Nexus is not switched on in this environment yet.";
  return "Could not send the question. Please try again.";
}
