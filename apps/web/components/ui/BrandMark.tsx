import { cx } from "./cx";

/**
 * The Nexus mark: three H3-style hexagons joined by a link line (cells linked across stations).
 * Drawn for the navy chrome: amber link, light hexes. `size` is the mark's height in px.
 */
export function BrandMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Nexus" className={cx("shrink-0", className)}>
      <defs>
        <linearGradient id="nx-hex" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5fd3dc" />
          <stop offset="1" stopColor="#1f8fa0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="#0e2d4b" />
      <path d="M9 9.5 L16 16 L23 12.5" stroke="#f2b544" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M16 22.5 L16 16" stroke="#f2b544" strokeWidth="2" strokeLinecap="round" />
      {[[9, 9.5], [23, 12.5], [16, 22.5]].map(([x, y], i) => (
        <polygon key={i} fill="url(#nx-hex)"
          points={Array.from({ length: 6 }, (_, k) => {
            const a = (Math.PI / 3) * k + Math.PI / 6;
            return `${(x + 4.2 * Math.cos(a)).toFixed(2)},${(y + 4.2 * Math.sin(a)).toFixed(2)}`;
          }).join(" ")} />
      ))}
      <circle cx="16" cy="16" r="2.4" fill="#f2b544" />
    </svg>
  );
}

/** Mark plus wordmark, for the header bars. `sub` is the small label after the name (e.g. "Console"). */
export function BrandLockup({ sub, className }: { sub?: string; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="flex items-baseline gap-1.5 leading-none">
        <span className="text-[17px] font-semibold tracking-tight text-brand-ink">Nexus</span>
        <span className="text-[13px] font-medium text-brand-muted">Chennai</span>
        {sub && <span className="ml-1 rounded-md bg-white/10 px-1.5 py-0.5 text-[11px] font-medium text-accent-bright">{sub}</span>}
      </span>
    </span>
  );
}

export default BrandMark;
