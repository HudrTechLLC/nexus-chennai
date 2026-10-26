"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, type Tone } from "@/components/ui";
import { approveRun, rejectRun, saveMapping } from "@/app/console/(app)/system/sources/onboard/actions";
import {
  clip, confidenceLabel, dqHits, mappingEdits, mappingIssues, POLL_MS, shouldPoll, STATUS_LABEL, STEPS, stepIndex,
  TRANSFORM_LABEL, TRANSFORMS, type MappingEdit, type OnboardingField, type OnboardingMapping, type OnboardingRun,
  type Transform,
} from "@/lib/onboarding";

/** DQ severity → chip tone (G3): errors red, warnings amber, info slate. */
const severityTone = (sev: string): Tone => {
  const v = sev.toLowerCase();
  return v === "error" || v === "high" ? "danger" : v.startsWith("warn") || v === "medium" ? "warn" : "low";
};

type Draft = Record<string, { unified_field: string | null; transform: Transform }>;
const toDraft = (rows: OnboardingMapping[]): Draft =>
  Object.fromEntries(rows.map((m) => [m.source_col, { unified_field: m.unified_field, transform: m.transform }]));

const cell = "px-2 py-1.5 align-top";
const select = "rounded-md border border-line bg-bg px-2 py-1 text-sm disabled:opacity-70";

/** One onboarding run (WS1-23): status, the proposed mapping (editable while proposed), DQ, and the decision. */
export function RunView({ initialRun, initialMappings, fields }: {
  initialRun: OnboardingRun; initialMappings: OnboardingMapping[]; fields: OnboardingField[];
}) {
  const [run, setRun] = useState(initialRun);
  const [mappings, setMappings] = useState(initialMappings);
  const [draft, setDraft] = useState<Draft>(() => toDraft(initialMappings));
  const [busy, setBusy] = useState<null | "save" | "approve" | "reject">(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [tick, setTick] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`/console/system/sources/onboard/${encodeURIComponent(run.run_id)}/status`, { cache: "no-store" });
      const out = await res.json();
      if (!out.ok) { setPollError(out.error ?? `HTTP ${res.status}`); return; }
      setPollError(null);
      setRun(out.run as OnboardingRun);
      setMappings(out.mappings as OnboardingMapping[]);
      setDraft(toDraft(out.mappings as OnboardingMapping[]));
    } catch {
      setPollError("Lost contact; retrying.");
    } finally {
      setTick((t) => t + 1); // re-arms the poll even when nothing changed
    }
  }, [run.run_id]);

  // Chained timeouts (never overlapping); stops at proposed (a person decides) and at the end.
  useEffect(() => {
    if (!shouldPoll(run.status)) return;
    let live = true;
    timer.current = setTimeout(async () => { if (live) await refresh(); }, POLL_MS);
    return () => { live = false; if (timer.current) clearTimeout(timer.current); };
  }, [run.status, tick, refresh]);

  const current: MappingEdit[] = useMemo(
    () => mappings.map((m) => ({ source_col: m.source_col, ...(draft[m.source_col] ?? { unified_field: m.unified_field, transform: m.transform }) })),
    [mappings, draft],
  );
  const edits = useMemo(() => mappingEdits(mappings, current), [mappings, current]);
  const issues = useMemo(() => mappingIssues(current, fields), [current, fields]);
  const fieldLabel = (f: string | null) => (f ? fields.find((x) => x.field === f)?.label ?? f : "Ignore");
  const examples = (col: string) => (run.profile ?? []).find((p) => p.column === col)?.examples ?? [];
  const editable = run.status === "proposed";
  const blocked = issues.missing.length > 0 || issues.duplicated.length > 0;

  const set = (col: string, patch: Partial<Draft[string]>) =>
    setDraft((d) => ({ ...d, [col]: { ...(d[col] ?? { unified_field: null, transform: "none" }), ...patch } }));

  async function act(kind: "save" | "approve" | "reject") {
    setBusy(kind);
    setMessage(null);
    const out = kind === "save" ? await saveMapping(run.run_id, edits)
      : kind === "approve" ? await approveRun(run.run_id, edits)
      : await rejectRun(run.run_id, reason);
    setBusy(null);
    if (!out.ok) { setMessage({ kind: "error", text: out.error }); return; }
    setMessage({ kind: "ok", text: kind === "save" ? "Changes saved." : kind === "approve" ? "Approved. The worker registers the view next." : "Rejected." });
    if (out.status) setRun((r) => ({ ...r, status: out.status as OnboardingRun["status"] })); // restarts the poll after approve
    await refresh();
  }

  const at = stepIndex(run.status);
  const stopped = run.status === "rejected" || run.status === "failed";

  return (
    <div className="space-y-6">
      {/* Status */}
      <section aria-label="Status" className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-baseline gap-3">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${run.status === "registered" ? "bg-signal-soft text-signal" : stopped ? "bg-red-100 text-red-700" : "bg-line"}`}>
            {STATUS_LABEL[run.status]}
          </span>
          {shouldPoll(run.status) && <span className="text-xs text-muted" aria-live="polite">Checking every {POLL_MS / 1000} s…</span>}
          {run.trace_run_id && (
            <Link href={`/console/system/trace/${encodeURIComponent(run.trace_run_id)}`} className="text-xs text-signal underline-offset-2 hover:underline">
              trace {run.trace_run_id} (Zetaris query ids, model receipts)
            </Link>
          )}
        </div>
        <ol className="mt-4 grid grid-cols-6 text-xs" aria-label="Progress">
          {STEPS.map((s, i) => {
            const done = i < at || (i === at && run.status === "registered");
            const current = i === at && !stopped && !done;
            const failedHere = i === at && stopped;
            return (
              <li key={s} className="relative flex flex-col items-center gap-1.5 text-center" aria-current={i === at ? "step" : undefined}>
                {i > 0 && (
                  <span aria-hidden className={`absolute right-1/2 top-[7px] h-0.5 w-full ${i <= at ? "bg-signal" : "bg-line"}`} />
                )}
                <span aria-hidden className={`relative z-[1] size-4 rounded-full ${
                  failedHere ? "bg-danger ring-4 ring-danger-soft"
                    : done ? "bg-signal"
                    : current ? "bg-surface ring-[3px] ring-inset ring-signal"
                    : "bg-surface ring-2 ring-inset ring-line"}`} />
                <span className={done || current ? "font-medium text-ink" : failedHere ? "font-medium text-danger" : "text-muted"}>{s}</span>
              </li>
            );
          })}
        </ol>
        {(run.status === "uploaded" || run.status === "profiling") && (
          <p className="mt-2 text-sm text-muted">The local worker picks the file up within about 15 s, profiles it through Zetaris and proposes a mapping (about 20–40 s).</p>
        )}
        {run.status === "failed" && <p role="alert" className="mt-2 text-sm text-red-600">Failed: {run.error ?? "no reason recorded"}</p>}
        {run.status === "rejected" && <p className="mt-2 text-sm">Rejected{run.reject_reason ? `: ${run.reject_reason}` : "."}</p>}
        {pollError && <p role="alert" className="mt-2 text-sm text-red-600">{pollError}</p>}
      </section>

      {/* Registered, not linked */}
      {(run.status === "approved" || run.status === "registering" || run.status === "registered") && (
        <section aria-label="Registration" className="rounded-xl border border-line bg-surface p-5 text-sm">
          <h2 className="font-semibold">{run.status === "registered" ? "Registered, not linked" : "Registering"}</h2>
          <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-3">
            <div><dt className="text-xs text-muted">Zetaris view</dt><dd className="font-mono text-xs">{run.view_name ?? `onboard_${run.source_key}`}</dd></div>
            <div><dt className="text-xs text-muted">Rows</dt><dd>{run.row_count?.toLocaleString("en-IN") ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted">DQ findings</dt><dd>{dqHits(run.dq).length} of {(run.dq ?? []).length} rules found something</dd></div>
          </dl>
          <label className="mt-3 flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={run.linking_enabled} disabled aria-describedby="ob-link-note" />
            Include in linking (after review)
          </label>
          <p id="ob-link-note" className="mt-1 text-xs text-muted">
            A newly onboarded source is queryable through its own view but is not part of the unified crime view or linking.
            Turning it on needs a reviewed change, not a click.
          </p>
        </section>
      )}

      {/* Mapping */}
      {mappings.length > 0 && (
        <section aria-labelledby="ob-mapping" className="rounded-xl border border-line bg-surface p-5">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 id="ob-mapping" className="font-semibold">Proposed mapping</h2>
            <span className="text-xs text-muted">
              {run.mapping_source === "model" ? "proposed by the model (fast lane, traced)" : run.mapping_source === "rules" ? "proposed by name rules (model unavailable)" : ""}
              {run.row_count != null && ` · ${run.row_count.toLocaleString("en-IN")} rows`}
            </span>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className={cell}>Source column</th>
                  <th className={cell}>Maps to</th>
                  <th className={cell}>Transform</th>
                  <th className={cell}>Confidence</th>
                  <th className={cell}>Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {mappings.map((m) => {
                  const d = draft[m.source_col] ?? { unified_field: m.unified_field, transform: m.transform };
                  const changed = d.unified_field !== m.unified_field || d.transform !== m.transform;
                  const ex = examples(m.source_col).slice(0, 2).map((v) => clip(v, 30));
                  return (
                    <tr key={m.source_col}>
                      <td className={cell}>
                        <div className="font-mono text-xs">{m.source_col}</div>
                        {ex.length > 0 && <div className="text-xs text-muted">e.g. {ex.join(" · ")}</div>}
                      </td>
                      <td className={cell}>
                        {editable ? (
                          <>
                            <label className="sr-only" htmlFor={`f-${m.source_col}`}>Unified field for {m.source_col}</label>
                            <select id={`f-${m.source_col}`} className={select} value={d.unified_field ?? ""}
                              onChange={(e) => set(m.source_col, { unified_field: e.target.value || null })}>
                              <option value="">Ignore this column</option>
                              {fields.map((f) => <option key={f.field} value={f.field}>{f.label}{f.required ? " *" : ""}</option>)}
                            </select>
                          </>
                        ) : (
                          <span className={d.unified_field ? "" : "text-muted"}>{d.unified_field ? fieldLabel(d.unified_field) : "Ignored"}</span>
                        )}
                        {d.unified_field === "lat" && d.transform === "latlong_lat" && (
                          <div className="text-xs text-muted">fills Latitude and Longitude (the view splits the pair)</div>
                        )}
                        {m.proposed_field !== d.unified_field && (
                          <div className="text-xs text-muted">proposed: {fieldLabel(m.proposed_field)}</div>
                        )}
                        {(changed || m.edited) && <div className="text-xs text-signal">{changed ? "changed, not saved" : "edited"}</div>}
                      </td>
                      <td className={cell}>
                        {editable ? (
                          <>
                            <label className="sr-only" htmlFor={`t-${m.source_col}`}>Transform for {m.source_col}</label>
                            <select id={`t-${m.source_col}`} className={select} value={d.transform}
                              onChange={(e) => set(m.source_col, { transform: e.target.value as Transform })}>
                              {TRANSFORMS.map((t) => <option key={t} value={t}>{TRANSFORM_LABEL[t]}</option>)}
                            </select>
                          </>
                        ) : (
                          <span className="text-xs text-muted">{TRANSFORM_LABEL[d.transform]}</span>
                        )}
                      </td>
                      <td className={`${cell} tabular-nums`}>
                        <span className="inline-flex items-center gap-2">
                          <span aria-hidden className="h-1.5 w-10 overflow-hidden rounded-full bg-surface-2 ring-1 ring-inset ring-line">
                            <span className="block h-full rounded-full bg-signal" style={{ width: `${Math.round((m.confidence ?? 0) * 100)}%` }} />
                          </span>
                          {confidenceLabel(m.confidence)}
                        </span>
                      </td>
                      <td className={`${cell} max-w-xs text-xs text-muted`}>{m.reason ?? ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div aria-live="polite" className="mt-2 text-xs">
            {issues.missing.length > 0 && <p className="text-red-600">Required fields not mapped: {issues.missing.map(fieldLabel).join(", ")}.</p>}
            {issues.duplicated.length > 0 && <p className="text-red-600">Mapped more than once: {issues.duplicated.map(fieldLabel).join(", ")}.</p>}
            {!blocked && <p className="text-muted">{editable ? "* required. " : ""}Every required field is mapped exactly once{current.some((c) => c.unified_field === "lat" && c.transform === "latlong_lat") ? " (Longitude comes from the combined Lat/Long column)" : ""}.</p>}
          </div>
        </section>
      )}

      {/* DQ */}
      {run.dq && (
        <section aria-labelledby="ob-dq" className="rounded-xl border border-line bg-surface p-5">
          <h2 id="ob-dq" className="font-semibold">Data quality findings</h2>
          {run.dq.length === 0 ? (
            <p className="mt-1 text-sm text-muted">No findings.</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm sm:min-w-[560px]">
                <thead className="text-left text-xs text-muted">
                  <tr><th className={cell}>Rule</th><th className={cell}>Severity</th><th className={cell}>Rows</th><th className={`${cell} hidden sm:table-cell`}>Sample</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {run.dq.map((f, i) => (
                    <tr key={`${f.rule}-${i}`} className={Number(f.count) > 0 ? "" : "text-muted"}>
                      <td className={cell}><div className="font-mono text-xs">{f.rule}</div>{f.detail && <div className="text-xs text-muted">{clip(f.detail, 160)}</div>}</td>
                      <td className={cell}><Badge tone={severityTone(f.severity)}>{f.severity}</Badge></td>
                      <td className={`${cell} tabular-nums`}>{Number(f.count).toLocaleString("en-IN")}</td>
                      <td className={`${cell} hidden text-xs text-muted sm:table-cell`}>{(f.sample_rows ?? []).slice(0, 2).map((r) => clip(r, 50)).join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Decision */}
      {editable && (
        <section aria-labelledby="ob-decide" className="space-y-3 rounded-xl border border-signal bg-surface p-5">
          <h2 id="ob-decide" className="font-semibold">Decide</h2>
          <p className="text-sm text-muted">Approving registers the mapped view <span className="font-mono text-xs">onboard_{run.source_key}</span> in Zetaris. The source stays out of linking.</p>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={!!busy || edits.length === 0} onClick={() => act("save")}
              className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-60">
              {busy === "save" ? "Saving…" : `Save changes${edits.length ? ` (${edits.length})` : ""}`}
            </button>
            <button type="button" disabled={!!busy || blocked} onClick={() => act("approve")}
              title={blocked ? "Map every required field exactly once first" : undefined}
              className="rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60">
              {busy === "approve" ? "Approving…" : edits.length ? "Save and approve" : "Approve"}
            </button>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[16rem] flex-1">
              <label htmlFor="ob-reason" className="text-xs text-muted">Reason for rejecting (optional)</label>
              <input id="ob-reason" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-md border border-line bg-bg px-3 py-2 text-sm" />
            </div>
            <button type="button" disabled={!!busy} onClick={() => act("reject")}
              className="rounded-md border border-red-300 px-3 py-2 text-sm text-red-700 disabled:opacity-60">
              {busy === "reject" ? "Rejecting…" : "Reject"}
            </button>
          </div>
        </section>
      )}
      <div aria-live="polite">
        {message && <p role={message.kind === "error" ? "alert" : undefined} className={`text-sm ${message.kind === "error" ? "text-red-600" : "text-signal"}`}>{message.text}</p>}
      </div>
    </div>
  );
}

export default RunView;
