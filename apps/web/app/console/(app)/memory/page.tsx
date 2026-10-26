import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { officerNames } from "@/lib/alertsData";
import { pct, REASON_LABEL } from "@/lib/alerts";
import { decisionsFor, fetchEffects, fetchLedgerPage, fetchMemories, fetchStateLedger } from "@/lib/memoryData";
import {
  ACTION_LABEL, actionLabel, confidenceChange, decisionLabel, LAYER_LABEL, memoryStories, parseLedgerFilter, summarise,
  type MemoryStory,
} from "@/lib/memory";
import { BandPill } from "@/components/console/alerts/AlertBits";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;
const fmt = (iso: string) => new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

function Confidence({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-bg" aria-hidden>
        <span className="block h-full rounded-full bg-signal" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="font-mono text-xs tabular-nums">{value.toFixed(2)}</span>
    </span>
  );
}

/** Confidence over time as a tiny step line (one point per ledger change). */
function Sparkline({ points, w = 120, h = 28 }: { points: number[]; w?: number; h?: number }) {
  if (points.length < 2) return null;
  const step = w / (points.length - 1);
  const d = points.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - 2 - v * (h - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`confidence ${points.map((p) => p.toFixed(2)).join(" → ")}`}>
      <path d={d} fill="none" stroke="var(--signal)" strokeWidth={1.5} />
    </svg>
  );
}

function StoryCard({ s, decider, decidedAt, note }: { s: MemoryStory; decider: string | null; decidedAt: string | null; note: string | null }) {
  const m = s.memory;
  const approved = decisionLabel(m.decision) === "Approved";
  return (
    <li className="rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm">
            <span className={`font-semibold ${approved ? "text-signal" : "text-red-600"}`}>{decisionLabel(m.decision)}</span>
            {m.alert_id && <> on <Link href={`/console/alerts/${encodeURIComponent(m.alert_id)}`} className="font-mono text-xs text-signal hover:underline">{m.alert_id}</Link></>}
            {m.reason_code && <> · {REASON_LABEL[m.reason_code as keyof typeof REASON_LABEL] ?? m.reason_code}</>}
            {decider && <span className="text-muted"> · by {decider}</span>}
            {decidedAt && <span className="text-muted"> · {fmt(decidedAt)}</span>}
          </p>
          {(note || m.note) && <p className="mt-1 text-sm italic text-muted">“{note ?? m.note}”</p>}
          <p className="mt-2 text-sm"><span className="text-muted">Remembered pattern:</span> {m.content}</p>
        </div>
        <div className="shrink-0 space-y-1 text-right text-xs text-muted">
          <p className="font-mono">{m.memory_id} · {LAYER_LABEL[m.layer] ?? m.layer}</p>
          <Confidence value={Number(m.confidence)} />
          <Sparkline points={s.history.map((h) => h.confidence)} />
        </div>
      </div>

      <div className="mt-3 border-t border-line pt-3">
        {s.applied.length === 0 ? (
          <p className="text-sm text-muted">Not applied to any later alert yet. It will change the score of the next similar pair.</p>
        ) : (
          <>
            <p className="text-sm font-medium">
              Changed {s.applied.length} later alert{s.applied.length === 1 ? "" : "s"}
              <span className="text-muted"> · {s.raised} raised, {s.lowered} lowered</span>
            </p>
            <ul className="mt-2 space-y-1">
              {s.applied.map((a) => {
                return (
                  <li key={a.alert_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                    <Link href={`/console/alerts/${encodeURIComponent(a.alert_id)}`} className="font-mono text-xs text-signal hover:underline">{a.alert_id}</Link>
                    <span className="font-mono tabular-nums" title="final score, after H-MEM and the Skeptic"><b>{pct(a.score)}</b></span>
                    <span className={`font-mono text-xs ${a.delta != null && a.delta < 0 ? "text-red-600" : "text-signal"}`}>{a.effect ?? "?"}</span>
                    <BandPill band={a.band} />
                    <span className="text-xs text-muted">{a.status}{a.shared > 1 ? ` · one adjustment from ${a.shared} memories` : ""} · {fmt(a.created_at)}</span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </li>
  );
}

export default async function MemoryPage({ searchParams }: { searchParams: { ledger?: string; page?: string } }) {
  await requireOfficer("analyst+");
  const filter = parseLedgerFilter(searchParams.ledger);
  const page = Math.max(0, Number.parseInt(searchParams.page ?? "0", 10) || 0);
  const sb = consoleServerClient();

  const [mem, effects, state, ledger] = await Promise.all([
    fetchMemories(sb), fetchEffects(sb), fetchStateLedger(sb), fetchLedgerPage(sb, filter, page, PAGE_SIZE),
  ]);
  const error = mem.error ?? effects.error ?? state.error ?? ledger.error;
  const stories = memoryStories(mem.rows, effects.rows, state.rows);
  const summary = summarise(mem.rows, effects.rows);
  const decisions = await decisionsFor(sb, mem.rows.map((m) => m.alert_id ?? ""));
  const names = await officerNames(sb, Object.values(decisions).map((d) => d.by));
  const pages = Math.max(1, Math.ceil(ledger.total / PAGE_SIZE));
  const href = (over: { ledger?: string; page?: number }) => {
    const p = new URLSearchParams();
    const l = over.ledger ?? filter;
    if (l !== "decisions") p.set("ledger", l);
    const pg = over.page ?? 0;
    if (pg > 0) p.set("page", String(pg));
    const s = p.toString();
    return `/console/memory${s ? `?${s}` : ""}#ledger`;
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Memory</h1>
        <p className="max-w-prose text-sm text-muted">
          What the system learned from analysts (H-MEM engine). Every approve or reject becomes a memory. When a later pair looks
          similar, the memory moves its score by a bounded amount (at most ±0.08 in total) and the alert shows it. The ledger below is
          append-only: every change is a line, and nothing is edited or deleted.
        </p>
      </div>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load memory: {error}</p>}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Memories", summary.memories, `${summary.approved} from approvals · ${summary.rejected} from rejections`],
          ["Mean confidence", summary.meanConfidence == null ? "—" : summary.meanConfidence.toFixed(2), `${summary.byLayer.long_term} long-term · ${summary.byLayer.working} working · ${summary.byLayer.short_term} short-term`],
          ["Later alerts changed", summary.alertsAdjusted, "scores adjusted by a memory"],
          ["Raised · lowered", `${summary.raised} · ${summary.lowered}`, "alerts pushed up · pushed down"],
        ].map(([label, value, sub]) => (
          <div key={String(label)} className="rounded-xl border border-line bg-surface p-4">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="text-2xl font-bold tabular-nums">{value}</dd>
            <dd className="text-xs text-muted">{sub}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="stories">
        <h2 id="stories" className="mb-2 text-lg font-semibold">How analyst decisions changed later scores</h2>
        {stories.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
            No memories yet. When an analyst approves or rejects a link alert, the worker records it in H-MEM and it appears here,
            followed by every later alert it changes.
          </p>
        ) : (
          <ul className="space-y-3">
            {stories.map((s) => {
              const d = s.memory.alert_id ? decisions[s.memory.alert_id] : undefined;
              return <StoryCard key={s.memory.id} s={s} decider={d ? names[d.by] ?? null : null} decidedAt={d?.at ?? null} note={d?.note ?? null} />;
            })}
          </ul>
        )}
      </section>

      <section id="ledger" aria-labelledby="ledger-h" className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="ledger-h" className="text-lg font-semibold">Trust ledger <span className="text-sm font-normal text-muted">· append-only · {ledger.total} entries</span></h2>
          <nav className="flex flex-wrap gap-1 text-xs" aria-label="Ledger filter">
            {["decisions", "all", ...Object.keys(ACTION_LABEL).filter((a) => ["create", "feedback", "read", "promote", "demote", "merge"].includes(a))].map((f) => (
              <Link key={f} href={href({ ledger: f })} aria-current={f === filter ? "true" : undefined}
                className={`rounded-md px-2 py-0.5 ${f === filter ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>
                {f === "decisions" ? "State changes" : f === "all" ? "All" : actionLabel(f)}
              </Link>
            ))}
          </nav>
        </div>
        {ledger.rows.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No ledger entries{filter === "decisions" || filter === "all" ? "" : ` of type “${actionLabel(filter)}”`} yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr><th className="py-1 pr-3 font-normal">When</th><th className="pr-3 font-normal">Action</th><th className="pr-3 font-normal">Memory</th><th className="pr-3 font-normal">Confidence</th><th className="pr-3 font-normal">Actor</th><th className="font-normal">Entry</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {ledger.rows.map((e) => {
                  const c = confidenceChange(e);
                  const kind = e.details?.details && typeof e.details.details.kind === "string" ? ` (${e.details.details.kind})` : "";
                  return (
                    <tr key={e.id}>
                      <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-muted">{fmt(e.at)}</td>
                      <td className="pr-3">{actionLabel(e.action)}{kind}</td>
                      <td className="pr-3 font-mono text-xs">{e.memory_id}</td>
                      <td className="whitespace-nowrap pr-3 font-mono text-xs tabular-nums">
                        {c.before != null && c.after != null ? `${c.before.toFixed(2)} → ${c.after.toFixed(2)}` : c.after != null ? c.after.toFixed(2) : "—"}
                      </td>
                      <td className="pr-3 text-xs">{e.actor}</td>
                      <td className="font-mono text-[11px] text-muted" title={e.entry_hash}>{e.entry_hash.slice(0, 10)}…</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="mt-3 flex items-center gap-3 text-sm">
            {page > 0 && <Link href={href({ page: page - 1 })} className="text-signal hover:underline">← Newer</Link>}
            <span className="text-xs text-muted">Page {page + 1} of {pages}</span>
            {page + 1 < pages && <Link href={href({ page: page + 1 })} className="text-signal hover:underline">Older →</Link>}
          </div>
        )}
      </section>
    </div>
  );
}
