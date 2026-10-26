import typography from "@tailwindcss/typography";
import type { Config } from "tailwindcss";

/** Colours are CSS variables (app/globals.css), so every class follows light/dark automatically. */
const v = (name: string) => `var(--${name})`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), "surface-2": v("surface-2"), ink: v("ink"), muted: v("muted"), line: v("line"),
        accent: v("accent"), "accent-soft": v("accent-soft"), "accent-bright": v("accent-bright"),
        signal: v("signal"), "signal-strong": v("signal-strong"), "signal-soft": v("signal-soft"), "on-signal": v("on-signal"),
        brand: v("brand"), "brand-2": v("brand-2"), "brand-ink": v("brand-ink"), "brand-muted": v("brand-muted"),
        "brand-line": v("brand-line"), "brand-hover": v("brand-hover"),
        ok: v("ok"), "ok-soft": v("ok-soft"), warn: v("warn"), "warn-soft": v("warn-soft"),
        danger: v("danger"), "danger-soft": v("danger-soft"), info: v("info"), "info-soft": v("info-soft"),
        "sev-high": v("sev-high"), "sev-high-soft": v("sev-high-soft"), "sev-low": v("sev-low"), "sev-low-soft": v("sev-low-soft"),
      },
      boxShadow: { card: v("shadow-card"), raised: v("shadow-raised") },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "Segoe UI Variable Text", "Segoe UI", "system-ui", "-apple-system", "Roboto", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Cascadia Mono", "Consolas", "monospace"],
      },
      backgroundImage: {
        "brand-bar": "linear-gradient(100deg, var(--brand) 0%, var(--brand-2) 100%)",
      },
      zIndex: { dropdown: "30", sticky: "40", drawer: "50", toast: "60" },
    },
  },
  plugins: [typography],
};
export default config;
