"use client";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import {
  EDGE_LABEL, forceLayout, neighbours, nodeLabel, nodeRadius, provenanceFor, TYPE_COLOUR, TYPE_LABEL,
  type GraphEdge, type GraphNode, type Provenance,
} from "@/lib/worldGraph";

const W = 1000;
const H = 640;

const fmt = (iso: string) => new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" });

/** Masks phone-like and Aadhaar-like digit runs in attribute values (spec J5). */
function mask(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.replace(/\d{6,}/g, (d) => `${"•".repeat(d.length - 4)}${d.slice(-4)}`);
}

function href(n: GraphNode): string | null {
  if (n.type === "crime") return `/console/cases/${encodeURIComponent(n.key)}`;
  if (n.type === "series") return `/console/series/${encodeURIComponent(n.key)}`;
  return null;
}

function ProvList({ rows }: { rows: Provenance[] }) {
  if (rows.length === 0) return <p className="text-xs text-muted">No observations recorded for this item.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {rows.map((p) => (
        <li key={p.source} className="flex justify-between gap-2">
          <span className="font-medium">{p.source}</span>
          <span className="text-right text-muted">{p.n}× · {fmt(p.first)}{p.last !== p.first ? ` → ${fmt(p.last)}` : ""}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * World Model explorer: entities as nodes (colour = type, size = degree), relations as edges.
 * Click a node or edge for its attributes and provenance (which agent or feed asserted it, how
 * often, when). Drag to pan, scroll to zoom. "Centre here" reloads the neighbourhood around a node.
 */
export function GraphExplorer({ nodes, edges, provenance, seedIds, qs }: {
  nodes: GraphNode[]; edges: GraphEdge[]; provenance: Provenance[]; seedIds: string[];
  qs: string; // current filters (hops, types) to keep when re-centring
}) {
  const pos = useMemo(() => {
    const p = forceLayout(nodes.map((n) => n.id), edges, { width: W, height: H, pin: seedIds.length === 1 ? seedIds[0] : null });
    return new Map(p.map((x) => [x.id, x]));
  }, [nodes, edges, seedIds]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const [sel, setSel] = useState<{ kind: "node" | "edge"; id: string } | null>(seedIds[0] ? { kind: "node", id: seedIds[0] } : null);
  const [hover, setHover] = useState<string | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  const focus = sel?.kind === "node" ? sel.id : hover;
  const near = useMemo(() => {
    if (!focus) return null;
    return new Set([focus, ...neighbours(focus, edges).map((x) => x.other)]);
  }, [focus, edges]);

  const selNode = sel?.kind === "node" ? byId.get(sel.id) : undefined;
  const selEdge = sel?.kind === "edge" ? edges.find((e) => e.id === sel.id) : undefined;

  const onWheel = (e: React.WheelEvent) => {
    const rect = svg.current?.getBoundingClientRect();
    if (!rect) return;
    const mx = ((e.clientX - rect.left) / rect.width) * W;
    const my = ((e.clientY - rect.top) / rect.height) * H;
    const k = Math.min(4, Math.max(0.4, view.k * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    setView({ k, x: mx - ((mx - view.x) / view.k) * k, y: my - ((my - view.y) / view.k) * k });
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <div className="relative overflow-hidden rounded-xl border border-line bg-surface">
        <svg
          ref={svg} viewBox={`0 0 ${W} ${H}`} className="h-[min(70vh,640px)] w-full touch-none select-none"
          role="img" aria-label={`World Model graph: ${nodes.length} entities, ${edges.length} relations`}
          onWheel={onWheel}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; }}
          onPointerMove={(e) => {
            const d = drag.current;
            const rect = svg.current?.getBoundingClientRect();
            if (!d || !rect) return;
            setView((v) => ({ ...v, x: d.vx + ((e.clientX - d.x) / rect.width) * W, y: d.vy + ((e.clientY - d.y) / rect.height) * H }));
          }}
          onPointerUp={() => { drag.current = null; }}
          onPointerLeave={() => { drag.current = null; }}
        >
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
            {edges.map((e) => {
              const a = pos.get(e.from);
              const b = pos.get(e.to);
              if (!a || !b) return null;
              const on = sel?.kind === "edge" && sel.id === e.id;
              const dim = near && !(near.has(e.from) && near.has(e.to));
              return (
                <g key={e.id} className="cursor-pointer" onClick={(ev) => { ev.stopPropagation(); setSel({ kind: "edge", id: e.id }); }}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={10} />
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={on ? "var(--ink)" : "var(--muted)"} strokeOpacity={dim ? 0.12 : on ? 1 : 0.5} strokeWidth={on ? 2.5 : 1.2} />
                </g>
              );
            })}
            {nodes.map((n) => {
              const p = pos.get(n.id);
              if (!p) return null;
              const r = nodeRadius(n.degree);
              const on = sel?.kind === "node" && sel.id === n.id;
              const dim = near && !near.has(n.id);
              const seed = seedIds.includes(n.id);
              return (
                <g key={n.id} transform={`translate(${p.x} ${p.y})`} className="cursor-pointer" opacity={dim ? 0.25 : 1}
                  onClick={(ev) => { ev.stopPropagation(); setSel({ kind: "node", id: n.id }); }}
                  onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
                  <circle r={r} fill={TYPE_COLOUR[n.type]} stroke={on || seed ? "var(--ink)" : "var(--surface)"} strokeWidth={on ? 3 : seed ? 2 : 1.5} />
                  {(r >= 8 || on || hover === n.id || seed || nodes.length <= 40) && (
                    <text y={r + 11} textAnchor="middle" fontSize={10} fill="var(--ink)" stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
                      {nodeLabel(n)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-2 rounded-md bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] px-2 py-1 text-[11px]">
          {Array.from(new Set(nodes.map((n) => n.type))).map((t) => (
            <span key={t} className="inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLOUR[t] }} />{TYPE_LABEL[t]}</span>
          ))}
        </div>
        <button type="button" onClick={() => setView({ x: 0, y: 0, k: 1 })}
          className="absolute bottom-2 right-2 rounded-md border border-line bg-surface px-2 py-1 text-xs text-muted hover:text-ink">Reset view</button>
      </div>

      <aside className="space-y-3">
        {!selNode && !selEdge && (
          <div className="rounded-xl border border-line bg-surface p-4 text-sm text-muted">
            Click an entity or a relation to see its attributes and provenance: which agent or feed asserted it, how many times, and when.
          </div>
        )}
        {selNode && (
          <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
            <div>
              <p className="font-mono text-xs uppercase tracking-widest" style={{ color: TYPE_COLOUR[selNode.type] }}>{TYPE_LABEL[selNode.type]}</p>
              <h2 className="break-all font-semibold">{selNode.type === "phone" ? mask(selNode.key) : selNode.key}</h2>
              <p className="break-all font-mono text-[11px] text-muted">{selNode.id}</p>
              {selNode.synthetic && <p className="text-[11px] text-accent">synthetic</p>}
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <Link href={`/console/graph?seed=${encodeURIComponent(selNode.id)}${qs ? `&${qs}` : ""}`} className="rounded-md bg-signal px-2 py-1 text-white">Centre here</Link>
              {href(selNode) && <Link href={href(selNode)!} className="rounded-md border border-line px-2 py-1 hover:border-signal">Open {selNode.type === "crime" ? "case" : "series"}</Link>}
            </div>
            {selNode.aliases.length > 0 && (
              <div className="text-xs"><p className="text-muted">Also written as</p><p>{selNode.aliases.map((a) => (selNode.type === "phone" ? mask(a) : a)).join(" · ")}</p></div>
            )}
            {Object.keys(selNode.attrs ?? {}).length > 0 && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                {Object.entries(selNode.attrs).slice(0, 16).map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="break-all">{mask(v)}</dd></div>
                ))}
              </dl>
            )}
            <div>
              <p className="mb-1 text-xs font-semibold">Provenance</p>
              <ProvList rows={provenanceFor(provenance, selNode.id)} />
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold">Relations in view ({neighbours(selNode.id, edges).length} of {selNode.degree})</p>
              <ul className="max-h-48 space-y-0.5 overflow-auto text-xs">
                {neighbours(selNode.id, edges).map(({ edge, other, out }) => {
                  const o = byId.get(other);
                  return (
                    <li key={edge.id}>
                      <button type="button" className="text-left hover:text-signal" onClick={() => setSel({ kind: "node", id: other })}>
                        {out ? "→" : "←"} {EDGE_LABEL[edge.type] ?? edge.type} <b>{o ? nodeLabel(o) : other}</b>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
            <p className="text-[11px] text-muted">First seen {fmt(selNode.created_at)} · updated {fmt(selNode.updated_at)}</p>
          </div>
        )}
        {selEdge && (
          <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
            <p className="font-mono text-xs uppercase tracking-widest text-muted">Relation</p>
            <p className="text-sm">
              <button type="button" className="font-semibold hover:text-signal" onClick={() => setSel({ kind: "node", id: selEdge.from })}>{byId.get(selEdge.from) ? nodeLabel(byId.get(selEdge.from)!) : selEdge.from}</button>
              {" "}<span className="text-muted">{EDGE_LABEL[selEdge.type] ?? selEdge.type}</span>{" "}
              <button type="button" className="font-semibold hover:text-signal" onClick={() => setSel({ kind: "node", id: selEdge.to })}>{byId.get(selEdge.to) ? nodeLabel(byId.get(selEdge.to)!) : selEdge.to}</button>
            </p>
            <p className="break-all font-mono text-[11px] text-muted">{selEdge.id}{selEdge.crime_id ? ` · case ${selEdge.crime_id}` : ""}</p>
            <div>
              <p className="mb-1 text-xs font-semibold">Provenance</p>
              <ProvList rows={provenanceFor(provenance, selEdge.id)} />
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

export default GraphExplorer;
