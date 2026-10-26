/**
 * Demo sign-ins shown under the console login form (judges' quick start).
 * The accounts come ONLY from the DEMO_LOGINS env var (JSON [{role,label,email,password}]) set on the
 * hosted deployment; nothing is in the repo. Unset or malformed means no panel, so local, docker and
 * fork builds show nothing.
 */

export type DemoLogin = { role: string; label: string; email: string; password: string };

/** Display order: station officers first, then analyst, supervisor, admin; env order within a role. */
const ROLE_ORDER = ["station_officer", "analyst", "supervisor", "admin"];

export function parseDemoLogins(raw: string | undefined | null): DemoLogin[] {
  if (!raw) return [];
  let v: unknown;
  try {
    v = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(v)) return [];
  const out: DemoLogin[] = [];
  for (const x of v) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    if (typeof o.email !== "string" || !o.email.includes("@") || typeof o.password !== "string" || !o.password) continue;
    const role = typeof o.role === "string" ? o.role : "";
    const label = typeof o.label === "string" && o.label.trim() ? o.label.trim() : role.replace(/_/g, " ") || o.email;
    out.push({ role, label, email: o.email.trim(), password: o.password });
  }
  const rank = (r: string) => {
    const i = ROLE_ORDER.indexOf(r);
    return i < 0 ? ROLE_ORDER.length : i;
  };
  return out
    .map((d, i) => ({ d, i }))
    .sort((a, b) => rank(a.d.role) - rank(b.d.role) || a.i - b.i)
    .map(({ d }) => d);
}

/** What a click on a demo account puts in the form (never submits). */
export function fillFrom(d: DemoLogin): { email: string; password: string } {
  return { email: d.email, password: d.password };
}
