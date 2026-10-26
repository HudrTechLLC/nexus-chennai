import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", surface: "var(--surface)", ink: "var(--ink)", muted: "var(--muted)",
        line: "var(--line)", accent: "var(--accent)", "accent-soft": "var(--accent-soft)",
        signal: "var(--signal)", "signal-soft": "var(--signal-soft)",
      },
    },
  },
  plugins: [],
};
export default config;
