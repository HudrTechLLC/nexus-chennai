"use client";
import { useRef } from "react";
import { DAY_MS } from "@/lib/pulse";

/**
 * Bottom bar (spec G3): daily-count histogram, a draggable window [from, to] where `to` is the
 * playhead, and Play (1 day per 100 ms by default).
 */
export function TimeScrubber({ min, max, from, to, bins, playing, onWindow, onPlay, speedMsPerDay }: {
  min: number; max: number; from: number; to: number; bins: number[]; playing: boolean;
  onWindow: (from: number, to: number) => void; onPlay: () => void; speedMsPerDay: number;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const drag = useRef<{ mode: "move" | "start" | "end"; x0: number; from: number; to: number } | null>(null);
  const span = Math.max(DAY_MS, max - min);
  const pct = (t: number) => ((t - min) / span) * 100;
  const peak = Math.max(1, ...bins);

  const begin = (mode: "move" | "start" | "end") => (e: React.PointerEvent) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    drag.current = { mode, x0: e.clientX, from, to };
  };
  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || !bar.current) return;
    const dt = ((e.clientX - d.x0) / bar.current.clientWidth) * span;
    if (d.mode === "move") {
      const len = d.to - d.from;
      const nf = Math.min(Math.max(min, d.from + dt), max - len);
      onWindow(nf, nf + len);
    } else if (d.mode === "start") onWindow(Math.min(Math.max(min, d.from + dt), d.to - DAY_MS), d.to);
    else onWindow(d.from, Math.max(Math.min(max, d.to + dt), d.from + DAY_MS));
  };
  const fmt = (t: number) => new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div className="rounded-xl bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] p-3 shadow-lg backdrop-blur">
      <div className="mb-1 flex items-center gap-3 text-xs">
        <button onClick={onPlay} className="rounded-md bg-signal px-3 py-1 font-medium text-white" aria-pressed={playing}>
          {playing ? "Pause" : "Play"}
        </button>
        <span className="font-mono">{fmt(from)} → {fmt(to)}</span>
        <span className="text-muted">{Math.round((to - from) / DAY_MS)} days · 1 day per {speedMsPerDay} ms</span>
      </div>
      <div ref={bar} className="relative h-14 select-none" onPointerMove={move} onPointerUp={() => { drag.current = null; }}>
        <div className="absolute inset-0 flex items-end gap-px" aria-hidden>
          {bins.map((n, i) => (
            <div key={i} className="flex-1 rounded-t-sm bg-[color-mix(in_srgb,var(--muted)_50%,transparent)]" style={{ height: `${(n / peak) * 100}%`, minHeight: n ? 2 : 0 }} />
          ))}
        </div>
        <div
          className="absolute inset-y-0 cursor-grab border-x-2 border-accent bg-[color-mix(in_srgb,var(--accent)_15%,transparent)]"
          style={{ left: `${pct(from)}%`, width: `${Math.max(0.5, pct(to) - pct(from))}%` }}
          onPointerDown={begin("move")}
          role="group" aria-label="Time window"
        >
          <span className="absolute inset-y-0 -left-1.5 w-3 cursor-ew-resize" onPointerDown={begin("start")} />
          <span className="absolute inset-y-0 -right-1.5 w-3 cursor-ew-resize" onPointerDown={begin("end")} />
        </div>
      </div>
    </div>
  );
}
