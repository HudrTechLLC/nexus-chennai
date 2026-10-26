"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { consoleBrowserClient } from "@/lib/supabase/browser";
import { AlertMapLoader } from "@/components/console/alerts/AlertMapLoader";
import {
  ASK_CRIME_COLUMNS, checkQuestion, crimeLabel, hitScenes, insertErrorText, isSettled, nextPoll, POLL_MS, QUESTION_MAX, RECENT_LIMIT, SAMPLE_QUESTIONS, STATUS_TEXT,
  visibleResults, type AskCrime, type AskQuestion, type AskResultRow,
} from "@/lib/ask";

const istDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "—";

type Phase =
  | { kind: "idle" }
  | { kind: "asking"; q: AskQuestion | null; startedAt: number }
  | { kind: "settled"; q: AskQuestion; rows: AskResultRow[]; hidden: number; detailsFailed: boolean }
  | { kind: "gave_up"; q: AskQuestion | null }
  | { kind: "error"; message: string };

/**
 * The Ask Nexus screen: question box with sample chips, live status while the worker plans and runs, then the
 * answer summary, the cited cases (each links to its case file), a map of the hits and "How this was answered".
 */
export function AskNexus({ canOpenTrace }: { canOpenTrace: boolean }) {
  const [text, setText] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [recent, setRecent] = useState<AskQuestion[]>([]);

  /** The officer's own last few questions (RLS: own rows only), so "check back" has somewhere to go. */
  async function loadRecent() {
    const { data } = await consoleBrowserClient().from("ask_questions").select("*").order("created_at", { ascending: false }).limit(RECENT_LIMIT);
    setRecent((data ?? []) as AskQuestion[]);
  }

  useEffect(() => {
    void loadRecent();
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, []);

  function reopen(q: AskQuestion) {
    if (timer.current) clearTimeout(timer.current);
    setText(q.question);
    if (isSettled(q.status)) void finish(q);
    else {
      const startedAt = Date.now();
      setPhase({ kind: "asking", q, startedAt });
      poll(q.question_id, startedAt);
    }
  }

  const busy = phase.kind === "asking";

  async function finish(q: AskQuestion) {
    const ids = (q.answer?.rows ?? []).map((r) => r.crime_id);
    let readable: AskCrime[] = [];
    let detailsFailed = false;
    if (ids.length) {
      // display fields through crimes RLS: an id this officer may not read never becomes a row
      const { data, error } = await consoleBrowserClient().from("crimes").select(ASK_CRIME_COLUMNS).in("crime_id", ids);
      readable = (data ?? []) as AskCrime[];
      detailsFailed = !!error;
    }
    const { rows, hidden } = visibleResults(q.answer?.rows ?? [], readable);
    setPhase({ kind: "settled", q, rows, hidden: detailsFailed ? 0 : hidden, detailsFailed });
    void loadRecent();
    requestAnimationFrame(() => resultsRef.current?.focus());
  }

  function poll(id: string, startedAt: number) {
    timer.current = setTimeout(async () => {
      const { data, error } = await consoleBrowserClient().from("ask_questions").select("*").eq("question_id", id).maybeSingle();
      if (error || !data) {
        setPhase({ kind: "error", message: "Lost track of the question. Please ask again." });
        return;
      }
      const q = data as AskQuestion;
      const next = nextPoll(q.status, Date.now() - startedAt);
      if (next === "done") await finish(q);
      else if (next === "gave_up") { setPhase({ kind: "gave_up", q }); void loadRecent(); }
      else {
        setPhase({ kind: "asking", q, startedAt });
        poll(id, startedAt);
      }
    }, POLL_MS);
  }

  async function ask(raw: string) {
    const c = checkQuestion(raw);
    if (!c.ok) { setHint(c.reason); return; }
    setHint(null);
    if (timer.current) clearTimeout(timer.current);
    const startedAt = Date.now();
    setPhase({ kind: "asking", q: null, startedAt });
    const { data, error } = await consoleBrowserClient().from("ask_questions").insert({ question: c.question }).select("question_id").single();
    if (error || !data) {
      setPhase({ kind: "error", message: insertErrorText(error) });
      return;
    }
    poll((data as { question_id: string }).question_id, startedAt);
    void loadRecent();
  }

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => { e.preventDefault(); void ask(text); }}
        className="space-y-3 rounded-xl border border-line bg-surface p-5"
      >
        <label htmlFor="ask-q" className="text-sm font-semibold">Your question</label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id="ask-q" value={text} onChange={(e) => setText(e.target.value)} maxLength={QUESTION_MAX} disabled={busy}
            placeholder="e.g. Chain snatchings in Adyar after 7 pm this month"
            className="min-w-0 flex-1 rounded-md border border-line bg-bg px-3 py-2 text-sm"
          />
          <button disabled={busy} className="rounded-md bg-signal px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            {busy ? "Asking…" : "Ask"}
          </button>
        </div>
        {hint && <p role="alert" className="text-sm text-red-600">{hint}</p>}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted">Try:</span>
          {SAMPLE_QUESTIONS.map((s) => (
            <button key={s} type="button" disabled={busy} onClick={() => { setText(s); void ask(s); }}
              className="rounded-full border border-line px-3 py-1 text-left hover:border-signal disabled:opacity-60">
              {s}
            </button>
          ))}
        </div>
      </form>

      {recent.length > 0 && (
        <details className="rounded-xl border border-line bg-surface px-5 py-3 text-sm">
          <summary className="cursor-pointer font-semibold">Your recent questions <span className="font-normal text-muted">({recent.length})</span></summary>
          <ul className="mt-2 divide-y divide-line">
            {recent.map((q) => (
              <li key={q.question_id}>
                <button type="button" disabled={busy} onClick={() => reopen(q)}
                  className="flex w-full flex-wrap items-baseline justify-between gap-x-3 py-2 text-left hover:text-signal disabled:opacity-60">
                  <span className="min-w-0 flex-1">{q.question}</span>
                  <span className="text-xs text-muted">{STATUS_TEXT[q.status]} · {istDate(q.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <p aria-live="polite" className="sr-only">
        {phase.kind === "asking" ? STATUS_TEXT[phase.q?.status ?? "queued"] : phase.kind === "settled" ? STATUS_TEXT[phase.q.status] : ""}
      </p>

      {phase.kind === "asking" && (
        <section className="rounded-xl border border-line bg-surface p-5 text-sm" data-testid="ask-status">
          <p className="font-medium"><span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-signal align-middle" />{STATUS_TEXT[phase.q?.status ?? "queued"]}</p>
          {phase.q?.plan?.understood && <p className="mt-1 text-muted">Understood: {phase.q.plan.understood}</p>}
          <p className="mt-1 text-xs text-muted">Usually 10–40 seconds: the plan is written by a model, the searches run on Zetaris.</p>
        </section>
      )}

      {phase.kind === "gave_up" && (
        <section className="rounded-xl border border-line bg-surface p-5 text-sm">
          <p className="font-medium">Still working on it.</p>
          <p className="mt-1 text-muted">The worker has not finished after two minutes. It may still answer: open it from Your recent questions in a little while.</p>
        </section>
      )}

      {phase.kind === "error" && <p role="alert" className="rounded-xl border border-line bg-surface p-5 text-sm text-red-600">{phase.message}</p>}

      {phase.kind === "settled" && (
        <div ref={resultsRef} tabIndex={-1} className="space-y-5 outline-none" data-testid="ask-result">
          <section className="rounded-xl border border-line bg-surface p-5">
            <p className="text-xs uppercase tracking-wider text-muted">{phase.q.question}</p>
            {phase.q.status === "failed" ? (
              <p className="mt-2 text-sm text-red-600">{phase.q.error ?? "Something went wrong. Please ask again."}</p>
            ) : (
              <p className="mt-2 text-lg">{phase.q.answer?.summary ?? "No answer."}</p>
            )}
            {phase.q.status === "answered" && phase.q.answer && (
              <p className="mt-1 text-xs text-muted">
                {phase.q.answer.total} {phase.q.answer.total === 1 ? "case" : "cases"} found
                {phase.q.answer.truncated ? `, showing the newest ${phase.q.answer.rows.length}` : ""}
                {phase.hidden > 0 ? ` · ${phase.hidden} more not visible to your access` : ""}
                {phase.detailsFailed ? " · couldn't load the case details, please ask again" : ""}
              </p>
            )}
          </section>

          {phase.rows.length > 0 && (
            <div className="grid gap-5 lg:grid-cols-5">
              <section className="overflow-x-auto rounded-xl border border-line bg-surface p-5 lg:col-span-3">
                <h2 className="mb-2 font-semibold">Cases</h2>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted">
                    <tr><th className="py-1 pr-3">Case</th><th className="py-1 pr-3">What · where</th><th className="py-1 pr-3">When</th><th className="py-1">Why it matched</th></tr>
                  </thead>
                  <tbody>
                    {phase.rows.map((r) => (
                      <tr key={r.crime_id} className="border-t border-line align-top">
                        <td className="whitespace-nowrap py-2 pr-3"><Link href={`/console/cases/${encodeURIComponent(r.crime_id)}`} className="font-mono text-xs text-signal hover:underline">{r.crime_id}</Link></td>
                        <td className="py-2 pr-3">
                          {crimeLabel(r)}
                          <div className="text-xs text-muted">{(r.station_id ?? "").replace(/^PS-/, "")}{r.address ? ` · ${r.address}` : ""}</div>
                        </td>
                        <td className="whitespace-nowrap py-2 pr-3 text-xs">{istDate(r.occurred_from)}</td>
                        <td className="py-2 text-xs">{r.why}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section className="self-start rounded-xl border border-line bg-surface p-5 lg:sticky lg:top-4 lg:col-span-2">
                <h2 className="mb-2 font-semibold">Where</h2>
                <AlertMapLoader scenes={hitScenes(phase.rows)} trail={[]} />
              </section>
            </div>
          )}

          <HowAnswered q={phase.q} canOpenTrace={canOpenTrace} />
        </div>
      )}

    </div>
  );
}

export function HowAnswered({ q, canOpenTrace }: { q: AskQuestion; canOpenTrace: boolean }) {
  const steps = q.plan?.steps ?? [];
  return (
    <details className="rounded-xl border border-line bg-surface p-5">
      <summary className="cursor-pointer font-semibold">
        How this was answered
        <span className="ml-2 text-sm font-normal text-muted">
          {steps.length} {steps.length === 1 ? "query" : "queries"}{q.model ? ` · ${q.model}` : ""}
        </span>
      </summary>
      {q.plan?.understood && <p className="mt-3 text-sm">Understood as: <strong>{q.plan.understood}</strong></p>}
      {(q.plan?.notes ?? []).length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs text-muted">
          {q.plan!.notes!.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      {(q.plan?.filters ?? []).length > 0 && (
        <p className="mt-1 text-xs text-muted">Filters: {q.plan!.filters.map((f) => f.label).join(" · ")}</p>
      )}
      {steps.length > 0 && (
        <ol className="mt-3 space-y-1.5 text-sm">
          {steps.map((s, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2 border-t border-line pt-1.5 first:border-t-0 first:pt-0">
              <span className="text-muted">{i + 1}.</span>
              <span>{s.purpose}</span>
              <span className="font-mono text-xs text-muted">{s.query}</span>
              {typeof s.rows === "number" && <span className="text-xs text-muted">{s.rows} rows</span>}
              {s.query_id && <span className="font-mono text-xs text-muted">query {s.query_id}</span>}
            </li>
          ))}
        </ol>
      )}
      {q.plan?.model_plan != null && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-muted">The model&apos;s raw plan</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-bg p-3 font-mono">{JSON.stringify(q.plan.model_plan, null, 2)}</pre>
        </details>
      )}
      <p className="mt-3 text-xs text-muted">
        Plan by {q.model ?? "—"}{q.routed_model && q.routed_model !== q.model ? ` (routed to ${q.routed_model})` : ""}
        {q.receipt_id ? <> · receipt <span className="font-mono">{q.receipt_id}</span></> : null}
        {q.run_id && canOpenTrace ? <> · <Link href={`/console/system/trace/${encodeURIComponent(q.run_id)}`} className="text-signal hover:underline">Full trace →</Link></> : null}
      </p>
    </details>
  );
}

export default AskNexus;
