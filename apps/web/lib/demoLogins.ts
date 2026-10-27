/**
 * Demo sign-ins shown under the console login form (judges' quick start).
 * The accounts come ONLY from the DEMO_LOGINS env var (JSON [{role,label,email,password?,station?}]) set on
 * the hosted deployment; nothing is in the repo. Unset or malformed means no panel, so local, docker and
 * fork builds show nothing.
 *
 * The admin account never carries a password to the browser: any admin password in the env is dropped
 * here (on the server), and its tile fills the email only, so the user types the password.
 */

export type DemoLogin = {
  role: string;
  label: string;
  email: string;
  /** null for admin: the user types it. */
  password: string | null;
  /** Station shown on officer tiles (from `station`, or the part of the label after " · "). */
  station: string | null;
};

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
    if (typeof o.email !== "string" || !o.email.includes("@")) continue;
    const role = typeof o.role === "string" ? o.role : "";
    const isAdmin = role === "admin";
    const password = isAdmin ? null : typeof o.password === "string" && o.password ? o.password : undefined;
    if (password === undefined) continue; // everyone but admin needs a password to fill
    const label = typeof o.label === "string" && o.label.trim() ? o.label.trim() : role.replace(/_/g, " ") || o.email;
    const fromLabel = label.includes(" · ") ? label.split(" · ").slice(1).join(" · ").trim() : "";
    const station = typeof o.station === "string" && o.station.trim() ? o.station.trim() : fromLabel || null;
    out.push({ role, label, email: o.email.trim(), password, station: role === "station_officer" ? station : null });
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

/**
 * What a click on a demo account puts in the form (never submits). Without a password (admin) the
 * password field is cleared, so an earlier pick's password is not left behind, and gets the focus.
 */
export function fillFrom(d: DemoLogin): { email: string; password: string; focusPassword: boolean } {
  return { email: d.email, password: d.password ?? "", focusPassword: d.password === null };
}
