// Nexus engines sidecar: a local HTTP service that runs the vendored Meterless
// TypeScript references (World Model, H-MEM, Markovian) for the Python facade
// `app.engines` (ENGINES_BACKEND=sidecar). The references are imported unmodified
// from ../<engine>/reference/src; everything here is Nexus glue (key normalisation,
// observation dedupe, the deterministic sample generator for dossiers).
//
//   npx tsx sidecar/server.ts            # listens on 127.0.0.1:8790 (ENGINES_SIDECAR_PORT)
//
// Every endpoint is POST with a JSON body, except GET /health. Local only: binds 127.0.0.1.

import http from "node:http";

import { WorldModel, canonicalJson, entityIdFromName, externalId, sha256Hex } from "../world-model/reference/src/index.ts";
import { HMEM } from "../hmem/reference/src/index.ts";
import { Markovian, resetRunSeq } from "../markovian/reference/src/index.ts";
import { sampleStepFn } from "./sampleGenerator.ts";

const PORT = Number(process.env.ENGINES_SIDECAR_PORT ?? 8790);
const SOURCE = "github.com/Meterless/Meterless@1742dec56a66e58eef9dda2d2b865823758ca8cd";

// ------------------------------------------------------------------ World Model

const KEY_SYSTEMS: Record<string, string> = {
  crime: "fir", vehicle: "plate", phone: "msisdn", place: "h3", evidence: "evidence", series: "series",
};
const ENTITY_TYPES = ["crime", "person", "vehicle", "place", "phone", "evidence", "series"];
const EDGE_TYPES = ["involves", "used_vehicle", "seen_at", "described_as", "linked_to", "member_of"];

function canonicalKey(type: string, key: string): string {
  const k = String(key).trim();
  if (type === "vehicle") return k.normalize("NFKD").toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (type === "phone") {
    const digits = k.replace(/\D/g, "");
    return digits.length >= 10 ? digits.slice(-10) : digits;
  }
  if (type === "place") return k.toLowerCase();
  return k;
}

type Prov = { source: string; observation_id: string };

class WorldGlue {
  world = new WorldModel({ namespace: "nexus", storage: "memory", clock: () => new Date(0) });
  observations = new Set<string>();
  provenance = new Map<string, Prov[]>();
  rawKeys = new Map<string, string[]>();
  firstKey = new Map<string, string>();
  edges = new Map<string, { id: string; from: string; type: string; to: string; provenance: Prov[] }>();

  private obsId(subject: string, source: string, payload: unknown): string {
    return "obs_" + sha256Hex(`${subject}|${source}|${canonicalJson(payload)}`).slice(0, 16);
  }

  private observe(subject: string, source: string, payload: unknown): [string, boolean] {
    const id = this.obsId(subject, source, payload);
    if (this.observations.has(id)) return [id, false];
    this.observations.add(id);
    return [id, true];
  }

  private resolve(id: string): string {
    return this.world.view("graph").entity(id)?.id ?? id;
  }

  async upsert(type: string, key: string, attrs: Record<string, unknown>, source: string): Promise<string> {
    if (!source || !String(source).trim()) throw new Error("World Model: every write carries provenance. No provenance, no write.");
    if (!ENTITY_TYPES.includes(type)) throw new Error(`unknown entity type ${type}`);
    const clean = Object.fromEntries(Object.entries(attrs ?? {}).filter(([, v]) => v !== null && v !== undefined));
    const keyed = type in KEY_SYSTEMS;
    const ck = keyed ? canonicalKey(type, key) : key;
    if (keyed && !ck) throw new Error(`empty key for ${type}`);
    const plannedId = keyed ? externalId(type, KEY_SYSTEMS[type], ck) : entityIdFromName(type, key);
    const existing = this.world.view("graph").entity(plannedId);
    // Dedupe identical observations so a re-ingest is a true no-op (same rule as the Python store).
    if (existing && this.observations.has(this.obsId(existing.id, source, { type, key, attrs: clean }))) {
      return existing.id;
    }
    const prov = { kind: "agent", by: source, at: new Date(0).toISOString() };
    const ent = await this.world.upsertEntity(
      keyed
        ? { type, externalKey: { system: KEY_SYSTEMS[type], id: ck }, name: key, attrs: clean, source: prov }
        : { type, name: key, attrs: clean, source: prov },
    );
    const [obsId, isNew] = this.observe(ent.id, source, { type, key, attrs: clean });
    if (isNew) {
      if (!this.firstKey.has(ent.id)) this.firstKey.set(ent.id, ck);
      const keys = this.rawKeys.get(ent.id) ?? [];
      if (!keys.includes(key)) keys.push(key);
      this.rawKeys.set(ent.id, keys);
      const p = this.provenance.get(ent.id) ?? [];
      p.push({ source, observation_id: obsId });
      this.provenance.set(ent.id, p);
    }
    return ent.id;
  }

  async relate(from: string, type: string, to: string, source: string): Promise<string> {
    if (!EDGE_TYPES.includes(type)) throw new Error(`unknown edge type ${type}`);
    const f = this.resolve(from);
    const t = this.resolve(to);
    for (const end of [f, t]) if (!this.world.view("graph").entity(end)) throw new Error(`edge endpoint ${end} does not exist`);
    const rel = await this.world.relate({ from: f, type, to: t, source: { kind: "agent", by: source, at: new Date(0).toISOString() } });
    const edge = this.edges.get(rel.id) ?? { id: rel.id, from: rel.from, type, to: rel.to, provenance: [] };
    const [obsId, isNew] = this.observe(rel.id, source, { edge: [f, type, t] });
    if (isNew) edge.provenance.push({ source, observation_id: obsId });
    this.edges.set(rel.id, edge);
    return rel.id;
  }

  async endpoint(ref: unknown, source: string): Promise<string> {
    if (typeof ref === "string") return ref;
    const r = ref as { type: string; key?: string; name?: string; attrs?: Record<string, unknown> };
    return this.upsert(r.type, String(r.key ?? r.name), r.attrs ?? {}, source);
  }

  snapshot() {
    const graph = this.world.view("graph");
    const entities = graph.query({}).map((e) => ({
      id: e.id, type: e.type, key: this.firstKey.get(e.id) ?? e.name ?? e.id, attrs: e.attrs,
      aliases: this.rawKeys.get(e.id) ?? [], provenance: this.provenance.get(e.id) ?? [],
    }));
    const aliases: Record<string, string> = {};
    for (const ev of this.world.events()) {
      if (ev.kind === "alias") {
        const a = ev.payload as unknown as { aliasId: string; primaryId: string };
        aliases[a.aliasId] = a.primaryId;
      }
    }
    const merge_queue = this.world.mergeQueue().map((p) => ({
      left: p.leftId, right: p.rightId, similarity: Math.round(p.similarity * 1000) / 1000, status: p.status,
    }));
    return { entities, edges: [...this.edges.values()], aliases, merge_queue, engine_events: this.world.events().length };
  }
}

let wm = new WorldGlue();

// ------------------------------------------------------------------------ H-MEM

let hmem = new HMEM({ actor: "analyst" });

function hmemOpen(dir: string | null, nowMs: number | null) {
  hmem = new HMEM({ persistDir: dir ?? undefined, actor: "analyst", clock: nowMs == null ? Date.now : () => nowMs });
}

// ------------------------------------------------------------------- Markovian

async function markovianRun(body: {
  series_id: string;
  config: { chunk_size: number; max_chunks: number; carryover_tokens: number; overlap_tokens: number };
  chunks: { record: Record<string, unknown>; line: string }[][];
  total: number;
}) {
  resetRunSeq();
  const engine = new Markovian({
    chunkConfig: {
      chunkSize: body.config.chunk_size, maxChunks: body.config.max_chunks,
      carryoverTokens: body.config.carryover_tokens, overlapTokens: body.config.overlap_tokens,
    },
    clock: () => 0,
  });
  const carryovers: string[] = [];
  const run = await engine.run({
    goal: `Series dossier ${body.series_id}`,
    mode: "RESEARCH",
    stepFn: sampleStepFn(body.chunks.map((c) => c.map((x) => x.record)), body.total),
    stopWhen: ({ step, carryover }) => {
      carryovers.push(carryover);
      return step >= body.chunks.length;
    },
    reflect: false,
  });
  if (run.status === "errored") throw new Error(`markovian run errored: ${run.error}`);
  const finalCarryover = carryovers.length ? carryovers[carryovers.length - 1] : "";
  return {
    status: run.status,
    token_label: run.tokenLabel,
    chunks: run.chunks.map((c, i) => ({
      record_ids: (body.chunks[i] ?? []).map((x) => String(x.record.id)),
      content: c.content,
      carryover_in: c.carryover,
      carryover_out: carryovers[i] ?? finalCarryover,
    })),
    final_carryover: finalCarryover,
    engine_efficiency: { totalTokensUsed: run.totalTokensUsed, tokensSaved: run.totalTokensSaved, efficiencyPercent: run.efficiencyPercent },
  };
}

// ---------------------------------------------------------------------- server

type Handler = (body: any) => Promise<unknown> | unknown;
const routes: Record<string, Handler> = {
  "/world_model/reset": () => { wm = new WorldGlue(); return { ok: true }; },
  "/world_model/ingest": async ({ entities, source }) => {
    const ids: string[] = [];
    for (const e of entities) ids.push(await wm.upsert(e.type, String(e.key ?? e.name ?? ""), e.attrs ?? {}, source));
    for (let i = 0; i < entities.length; i++) {
      for (const edge of entities[i].edges ?? []) {
        if ("to" in edge) await wm.relate(ids[i], edge.type, await wm.endpoint(edge.to, source), source);
        else if ("from" in edge) await wm.relate(await wm.endpoint(edge.from, source), edge.type, ids[i], source);
        else throw new Error("edge needs 'to' or 'from'");
      }
    }
    return { ids };
  },
  "/world_model/snapshot": () => wm.snapshot(),
  "/hmem/open": ({ dir, now_ms }) => { hmemOpen(dir ?? null, now_ms ?? null); return { ok: true }; },
  "/hmem/add": ({ content, source, tags, confidence, provenance }) => {
    const rec = hmem.add({ content, source, tags, confidence, provenance });
    return { id: rec.id, tags: rec.tags };
  },
  "/hmem/query": ({ text }) => {
    const res = hmem.query(text);
    return { hits: res.memories.map((m) => ({ id: m.memory.id, tags: m.memory.tags, relevance: m.relevance })) };
  },
  "/hmem/feedback": ({ id, kind }) => { hmem.feedback(id, kind); return { ok: true }; },
  "/hmem/ledger": () => ({ entries: hmem.ledger.all() }),
  "/hmem/records": () => ({
    records: hmem.store.all().map(({ embedding: _e, ...rest }) => rest),
  }),
  "/markovian/run": (body) => markovianRun(body),
};

// Namespaces: each client (x-engines-ns header, default "default") gets its own World Model
// and H-MEM, so concurrent users (e.g. two lanes' test runs) never see each other's state.
// Requests are handled one at a time: handlers await, and the active state is swapped per request.
type NsState = { wm: WorldGlue; hmem: HMEM; lastUsed: number };
const namespaces = new Map<string, NsState>();
const MAX_NAMESPACES = 64;
let queue: Promise<unknown> = Promise.resolve();

function activate(ns: string): NsState {
  let st = namespaces.get(ns);
  if (!st) {
    st = { wm: new WorldGlue(), hmem: new HMEM({ actor: "analyst" }), lastUsed: 0 };
    namespaces.set(ns, st);
    if (namespaces.size > MAX_NAMESPACES) {
      const oldest = [...namespaces.entries()].filter(([k]) => k !== ns).sort((a, b) => a[1].lastUsed - b[1].lastUsed)[0];
      if (oldest) namespaces.delete(oldest[0]);
    }
  }
  st.lastUsed = Date.now();
  wm = st.wm;
  hmem = st.hmem;
  return st;
}

const server = http.createServer(async (req, res) => {
  const send = (code: number, obj: unknown) => {
    res.writeHead(code, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  if (req.method === "GET" && req.url === "/health") return send(200, { ok: true, source: SOURCE, engines: ["world_model", "hmem", "markovian"] });
  const handler = req.method === "POST" ? routes[req.url ?? ""] : undefined;
  if (!handler) return send(404, { error: `no route ${req.method} ${req.url}` });
  let raw = "";
  for await (const chunk of req) raw += chunk;
  const ns = String(req.headers["x-engines-ns"] ?? "default").slice(0, 128);
  const run = queue.then(async () => {
    const st = activate(ns);
    try {
      return { code: 200, body: await handler(raw ? JSON.parse(raw) : {}) };
    } catch (err) {
      return { code: 400, body: { error: (err as Error).message } };
    } finally {
      st.wm = wm; // reset/open replace the instances; keep them with this namespace
      st.hmem = hmem;
    }
  });
  queue = run.catch(() => undefined);
  const out = await run;
  send(out.code, out.body);
});

server.listen(PORT, "127.0.0.1", () => console.log(`engines sidecar listening on http://127.0.0.1:${PORT} (${SOURCE})`));
