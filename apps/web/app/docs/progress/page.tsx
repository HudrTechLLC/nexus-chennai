import type { Metadata } from "next";
import { Countdown } from "@/components/Countdown";
import { getTracker, type Task, type TaskStatus } from "@/lib/docs";

export const metadata: Metadata = { title: "Progress · Nexus Engg Docs" };

// =====================
// Status encoding (color + icon + label, never color alone)
// =====================

const STATUS: Record<TaskStatus, { color: string; icon: string }> = {
  done: { color: "#0ca30c", icon: "✓" },
  in_progress: { color: "var(--signal)", icon: "◐" },
  blocked: { color: "#d03b3b", icon: "!" },
  todo: { color: "var(--todo)", icon: "○" },
  cut: { color: "transparent", icon: "✂" },
};
const STACK: TaskStatus[] = ["done", "in_progress", "blocked", "todo"];

function counts(tasks: Task[]) {
  const c: Record<TaskStatus, number> = { done: 0, in_progress: 0, blocked: 0, todo: 0, cut: 0 };
  for (const t of tasks) c[t.status] += 1;
  return c;
}

/** One horizontal stacked bar: done / in progress / blocked / to do (cut tasks excluded). */
function StackBar({ tasks, label, sub }: { tasks: Task[]; label: string; sub?: string }) {
  const c = counts(tasks);
  const total = tasks.length - c.cut;
  const pct = total ? Math.round((c.done / total) * 100) : 0;
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-3 sm:grid-cols-[13rem_1fr_5rem]">
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">{label}</div>
        {sub && <div className="truncate text-xs text-muted">{sub}</div>}
      </div>
      <div className="flex h-4 gap-[2px] overflow-hidden rounded" role="img" aria-label={`${label}: ${c.done} of ${total} done`}>
        {STACK.filter((s) => c[s] > 0).map((s) => (
          <div
            key={s}
            title={`${label} · ${s.replace("_", " ")}: ${c[s]} task${c[s] === 1 ? "" : "s"}`}
            className="h-full first:rounded-l last:rounded-r"
            style={{ width: `${(c[s] / total) * 100}%`, background: STATUS[s].color }}
          />
        ))}
      </div>
      <div className="text-right text-sm tabular-nums">
        <span className="font-semibold">{pct}%</span> <span className="text-muted">{c.done}/{total}</span>
      </div>
    </div>
  );
}

function Badge({ status, label }: { status: TaskStatus; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold">
      <span
        aria-hidden
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] text-white"
        style={{ background: status === "cut" || status === "todo" ? "var(--muted)" : STATUS[status].color }}
      >
        {STATUS[status].icon}
      </span>
      {label}
    </span>
  );
}

export default function ProgressPage() {
  const t = getTracker();
  const all = t.workstreams.flatMap((w) => w.tasks);
  const c = counts(all);
  const scope = all.length - c.cut;
  const pct = scope ? Math.round((c.done / scope) * 100) : 0;
  const blockers = all.filter((x) => x.status === "blocked");
  const active = all.filter((x) => x.status === "in_progress");
  const phases = Object.keys(t.phases);
  const updated = new Date(t.updated).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="grid gap-8">
      <section className="grid gap-2">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">Workstreams · progress</p>
        <h1 className="text-4xl font-bold">Where we are</h1>
        <p className="text-sm text-muted">
          Updated {updated} IST. Source: <code>engg/docs/workstreams.json</code>, updated as work lands and redeployed on every merge.
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <div className="rounded-xl border border-line bg-surface p-4">
          <p className="font-mono text-xs uppercase tracking-widest text-muted">Overall</p>
          <p className="mt-1 text-5xl font-bold tabular-nums">{pct}%</p>
          <p className="text-sm text-muted">{c.done} of {scope} tasks done · {c.cut} cut to future work</p>
          <ul className="mt-3 grid grid-cols-2 gap-1 text-sm">
            {(["done", "in_progress", "blocked", "todo"] as TaskStatus[]).map((s) => (
              <li key={s} className="flex items-center justify-between gap-2">
                <Badge status={s} label={t.statuses[s]} />
                <span className="tabular-nums">{c[s]}</span>
              </li>
            ))}
          </ul>
        </div>
        <Countdown target={t.target_submit} deadline={t.deadline} />
      </section>

      <section className="grid gap-3 rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-bold">By workstream</h2>
          <Legend statuses={t.statuses} />
        </div>
        {t.workstreams.map((w) => (
          <StackBar key={w.id} tasks={w.tasks} label={`${w.id} ${w.name}`} sub={w.focus} />
        ))}
      </section>

      <section className="grid gap-3 rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-bold">By phase</h2>
          <p className="text-xs text-muted">Smallest submittable version: P0–P6 + P10</p>
        </div>
        {phases.map((p) => {
          const tasks = all.filter((x) => x.phase === p);
          if (!tasks.some((x) => x.status !== "cut")) {
            return (
              <div key={p} className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 text-sm text-muted sm:grid-cols-[13rem_1fr]">
                <span className="truncate">{p} {t.phases[p]}</span>
                <span>Cut to future work</span>
              </div>
            );
          }
          return <StackBar key={p} tasks={tasks} label={`${p} ${t.phases[p]}`} />;
        })}
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-xl font-bold">Blockers ({blockers.length})</h2>
          <TaskList tasks={blockers} statuses={t.statuses} />
        </div>
        <div className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-xl font-bold">In progress ({active.length})</h2>
          <TaskList tasks={active} statuses={t.statuses} />
        </div>
      </section>

      <section className="grid gap-6">
        <h2 className="text-2xl font-bold">All tasks to finish the project</h2>
        {t.workstreams.map((w) => (
          <div key={w.id} className="overflow-x-auto rounded-xl border border-line bg-surface">
            <div className="border-b border-line px-4 py-3">
              <h3 className="text-lg font-bold">{w.id} · {w.name}</h3>
              <p className="text-sm text-muted">{w.focus}</p>
            </div>
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="font-mono text-xs uppercase text-muted">
                <tr>
                  <th className="px-4 py-2">ID</th>
                  <th className="px-2 py-2">Phase</th>
                  <th className="px-2 py-2">Task</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-4 py-2">Note</th>
                </tr>
              </thead>
              <tbody>
                {w.tasks.map((x) => (
                  <tr key={x.id} className={`border-t border-line align-top ${x.status === "cut" ? "text-muted" : ""}`}>
                    <td className="px-4 py-2 font-mono text-xs">{x.id}</td>
                    <td className="px-2 py-2 font-mono text-xs">{x.phase}</td>
                    <td className={`px-2 py-2 ${x.status === "cut" ? "line-through" : ""}`}>{x.title}</td>
                    <td className="px-2 py-2"><Badge status={x.status} label={t.statuses[x.status]} /></td>
                    <td className="px-4 py-2 text-muted">
                      {x.note}
                      {x.ref && <span className="ml-1 font-mono text-xs">PR {x.ref}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </div>
  );
}

function Legend({ statuses }: { statuses: Record<TaskStatus, string> }) {
  return (
    <ul className="flex flex-wrap gap-3 text-xs">
      {STACK.map((s) => (
        <li key={s} className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-3 w-3 rounded-sm" style={{ background: STATUS[s].color }} />
          {statuses[s]}
        </li>
      ))}
    </ul>
  );
}

function TaskList({ tasks, statuses }: { tasks: Task[]; statuses: Record<TaskStatus, string> }) {
  if (!tasks.length) return <p className="mt-2 text-sm text-muted">None.</p>;
  return (
    <ul className="mt-2 grid gap-2 text-sm">
      {tasks.map((x) => (
        <li key={x.id} className="grid gap-0.5">
          <div className="flex items-start justify-between gap-2">
            <span><span className="font-mono text-xs text-muted">{x.id}</span> {x.title}</span>
            <Badge status={x.status} label={statuses[x.status]} />
          </div>
          {x.note && <span className="text-xs text-muted">{x.note}</span>}
        </li>
      ))}
    </ul>
  );
}
