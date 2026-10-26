/** Decorative hexagon field for a hero band (the map's own shape). Pure SVG, behind the content, hidden from AT. */
export function HexPattern() {
  return (
    <svg aria-hidden="true" focusable="false" className="pointer-events-none absolute inset-y-0 right-0 -z-10 h-full w-2/3 text-signal opacity-[0.14] [mask-image:linear-gradient(to_left,black,transparent)]">
      <defs>
        <pattern id="hero-hex" width="28" height="48.5" patternUnits="userSpaceOnUse" patternTransform="scale(1.2)">
          <path d="M14 0l14 8.08v16.17L14 32.33 0 24.25V8.08z M14 32.33V48.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#hero-hex)" />
    </svg>
  );
}
