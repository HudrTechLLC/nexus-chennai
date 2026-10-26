"use client";
import { useRef } from "react";
import { hhmm } from "@/lib/pulse";

/**
 * 24-hour radial dial (spec G3 clock filter). Drag across the ring to select an arc of hours;
 * the inside shows a polar histogram of the crimes in the current selection by hour.
 */
export function ClockDial({ arc, onChange, hours, size = 150 }: {
  arc: [number, number] | null;
  onChange: (arc: [number, number] | null) => void;
  hours: number[];
  size?: number;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const drag = useRef<number | null>(null);
  const c = size / 2;
  const rOuter = c - 6;
  const rInner = c - 26;
  const max = Math.max(1, ...hours);

  const minuteAt = (e: React.PointerEvent) => {
    const box = ref.current!.getBoundingClientRect();
    const x = e.clientX - box.left - c, y = e.clientY - box.top - c;
    const ang = (Math.atan2(x, -y) * 180) / Math.PI; // 0 at top, clockwise
    return Math.round((((ang + 360) % 360) / 360) * 1440 / 15) * 15 % 1440;
  };
  const pt = (m: number, r: number) => {
    const a = (m / 1440) * 2 * Math.PI;
    return [c + Math.sin(a) * r, c - Math.cos(a) * r];
  };
  const arcPathD = (s: number, e: number, r: number) => {
    const span = ((e - s + 1440) % 1440) || 1440;
    const [x1, y1] = pt(s, r), [x2, y2] = pt(s + span, r);
    return `M ${x1} ${y1} A ${r} ${r} 0 ${span > 720 ? 1 : 0} 1 ${x2} ${y2}`;
  };

  return (
    <div className="rounded-xl bg-[color-mix(in_srgb,var(--surface)_90%,transparent)] p-2 shadow-lg backdrop-blur">
      <svg
        ref={ref} width={size} height={size} className="touch-none select-none"
        role="slider" aria-label="Time of day filter" aria-valuetext={arc ? `${hhmm(arc[0])} to ${hhmm(arc[1])}` : "all day"}
        onPointerDown={(e) => { (e.target as Element).setPointerCapture(e.pointerId); drag.current = minuteAt(e); onChange([drag.current, (drag.current + 15) % 1440]); }}
        onPointerMove={(e) => { if (drag.current !== null) onChange([drag.current, minuteAt(e)]); }}
        onPointerUp={() => { drag.current = null; }}
      >
        <circle cx={c} cy={c} r={rOuter} fill="none" stroke="var(--line)" strokeWidth={14} />
        {hours.map((n, h) => {
          const r = 8 + ((rInner - 8) * n) / max;
          const [x1, y1] = pt(h * 60, 8), [x2, y2] = pt(h * 60 + 60, 8);
          const [x3, y3] = pt(h * 60 + 60, r), [x4, y4] = pt(h * 60, r);
          return <path key={h} d={`M ${x1} ${y1} L ${x4} ${y4} L ${x3} ${y3} L ${x2} ${y2} Z`} fill="var(--signal)" opacity={n ? 0.75 : 0.08} />;
        })}
        {arc && <path d={arcPathD(arc[0], arc[1], rOuter)} fill="none" stroke="var(--accent)" strokeWidth={14} strokeLinecap="round" />}
        {[0, 6, 12, 18].map((h) => {
          const [x, y] = pt(h * 60, rOuter);
          return <text key={h} x={x} y={y + 3} textAnchor="middle" fontSize={9} fill="var(--ink)">{h}</text>;
        })}
      </svg>
      <div className="flex items-center justify-between px-1 text-xs">
        <span className="font-mono">{arc ? `${hhmm(arc[0])}–${hhmm(arc[1])}` : "All day"}</span>
        {arc && <button className="text-muted hover:text-ink" onClick={() => onChange(null)}>clear</button>}
      </div>
    </div>
  );
}
