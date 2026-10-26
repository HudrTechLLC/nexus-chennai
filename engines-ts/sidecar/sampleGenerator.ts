// Deterministic, extractive step function for series dossiers (sample mode).
// Mirrors make_sample_generator in services/api/app/engines/markovian/__init__.py
// line for line (except the completion marker, see below), so both backends produce the same notes. State crosses chunks
// only through the carryover block the Markovian orchestrator hands back.

type Rec = Record<string, unknown>;

const TEXT_KEYS = ["text", "summary", "narrative", "description", "statement", "content", "title"];
const DATE_KEYS = ["date", "occurred_at", "reported_at", "created_at", "at"];
const STOP = new Set(
  `a an the and or of to in on at by for with from was were is are be been this that it its his her
their they he she them as after before near into over under one two three about also not no`.split(/\s+/),
);
const LEAD_KINDS = ["tip", "lead", "call", "anpr", "witness"];

const dateOf = (r: Rec) => {
  for (const k of DATE_KEYS) if (r[k]) return String(r[k]).slice(0, 10);
  return "undated";
};
const bodyOf = (r: Rec) => {
  for (const k of TEXT_KEYS) {
    const v = r[k];
    if (typeof v === "string" && v.trim()) return v.trim().split(/\s+/).join(" ");
  }
  return "";
};

class Counter {
  m = new Map<string, number>();
  add(k: string, n = 1) {
    this.m.set(k, (this.m.get(k) ?? 0) + n);
  }
  mostCommon(n: number): [string, number][] {
    return [...this.m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n); // stable: ties keep insertion order
  }
}

function parseState(carryover: string): { read: number; terms: Counter; leads: string[] } {
  let read = 0;
  const terms = new Counter();
  let leads: string[] = [];
  const c = carryover.match(/COMPLETED: read (\d+)/);
  if (c) read = Number(c[1]);
  const d = carryover.match(/DECISIONS: recurring MO ([^\n]*)/);
  if (d) {
    for (const part of d[1].split(",")) {
      const t = part.match(/^\s*([^\s]+) x(\d+)/);
      if (t) terms.add(t[1], Number(t[2]));
    }
  }
  const l = carryover.match(/CONTEXT: open leads ([^\n]*)/);
  if (l && l[1].trim() !== "none") leads = l[1].split(",").map((x) => x.trim()).filter(Boolean);
  return { read, terms, leads };
}

function termsOf(r: Rec): string[] {
  let mo = (r.mo_tags ?? r.mo ?? []) as unknown;
  if (typeof mo === "string") mo = [mo];
  const joined = (mo as unknown[]).map(String).join(" ").toLowerCase();
  let words = (joined.match(/[a-z][a-z0-9-]{2,}/g) ?? []).filter((w) => !STOP.has(w));
  if (!words.length) words = (bodyOf(r).toLowerCase().match(/[a-z][a-z0-9-]{3,}/g) ?? []).filter((w) => !STOP.has(w));
  return [...new Set(words)];
}

export function sampleStepFn(batches: Rec[][], total: number) {
  return ({ carryover, step }: { goal: string; carryover: string; step: number; prompt: string }) => {
    const batch = batches[step] ?? [];
    const { read: prevRead, terms, leads } = parseState(carryover);
    const notes: string[] = [];
    for (const rec of batch) {
      const body = bodyOf(rec);
      const first = body ? body.split(/(?<=[.!?])\s/)[0].slice(0, 160) : "(no text)";
      notes.push(`- [${rec.id}] ${dateOf(rec)} ${rec.kind ?? "record"}: ${first}`);
      for (const t of termsOf(rec)) terms.add(t);
      const status = String(rec.status ?? "open").toLowerCase();
      if (LEAD_KINDS.includes(String(rec.kind ?? "").toLowerCase()) && status !== "closed") leads.push(String(rec.id));
    }
    const read = prevRead + batch.length;
    const top = terms.mostCommon(8).map(([t, n]) => `${t} x${n}`).join(", ") || "none yet";
    const leadS = leads.slice(-6).join(", ") || "none";
    const state =
      `COMPLETED: read ${read} of ${total} records\nREMAINING: ${total - read} records\n` +
      `DECISIONS: recurring MO ${top}\nCONTEXT: open leads ${leadS}`;
    // No [TASK_COMPLETE] here: the orchestrator skips stopWhen on a completed chunk, and the
    // sidecar ends the chain through stopWhen (last planned batch) to capture the final carryover.
    return { content: notes.join("\n") + `\n\n[STATE_CHECKPOINT]\n${state}` };
  };
}
