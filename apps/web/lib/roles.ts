/**
 * Police roles and what each may open in the console (spec G2).
 * Pure data + helpers so the nav, the pages and the tests share one source.
 */

export const ROLES = ["station_officer", "analyst", "supervisor", "admin"] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_LABEL: Record<Role, string> = {
  station_officer: "Station officer",
  analyst: "Analyst",
  supervisor: "Supervisor",
  admin: "Admin",
};

/** Ranks for the "analyst+" / "supervisor+" rules in G2. Station officers are not ranked above analysts. */
const RANK: Record<Role, number> = { station_officer: 0, analyst: 1, supervisor: 2, admin: 3 };

export type Access = "all" | "analyst+" | "supervisor+" | "admin" | Role[];

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

/** True when `role` may open a screen with the given access rule. */
export function allows(role: Role | null | undefined, access: Access): boolean {
  if (!role) return false;
  if (access === "all") return true;
  if (access === "analyst+") return RANK[role] >= RANK.analyst;
  if (access === "supervisor+") return RANK[role] >= RANK.supervisor;
  if (access === "admin") return role === "admin";
  return access.includes(role);
}

/** Who may approve or reject a link alert (spec G2: analyst, supervisor; admin too, per Part I). */
export function canDecideAlerts(role: Role | null | undefined): boolean {
  return allows(role, ["analyst", "supervisor", "admin"]);
}

/**
 * `hidden`: the screen is not built yet, so the link is not shown (main must never link to a 404).
 * `desktop: "bell"`: left out of the wide sidebar because the header bell already links there
 * (the phone menu still lists it). `group` and `icon` are presentation only (ConsoleNav); access never depends on them.
 */
export type NavGroupKey = "home" | "investigate" | "links" | "public" | "system";
export type NavItem = {
  href: string; label: string; access: Access; group: NavGroupKey; icon: string; hidden?: boolean; desktop?: "bell";
};

/** Sidebar sections, in workflow order. "home" has no heading. */
export const NAV_GROUPS: { key: NavGroupKey; label: string | null }[] = [
  { key: "home", label: null },
  { key: "investigate", label: "Investigate" },
  { key: "links", label: "Alerts & series" },
  { key: "public", label: "Public" },
  { key: "system", label: "Data & system" },
];

/** Console navigation, grouped and in workflow order. Items the role cannot open are hidden. */
export const NAV: NavItem[] = [
  { href: "/console", label: "Overview", access: "all", group: "home", icon: "overview" },
  { href: "/console/map", label: "Pulse Map", access: "all", group: "home", icon: "map" },
  { href: "/console/ask", label: "Ask", access: "analyst+", group: "home", icon: "ask" }, // WS3-30 Ask Nexus
  { href: "/console/notifications", label: "Notifications", access: "all", group: "home", icon: "bell", desktop: "bell" },
  { href: "/console/cases", label: "Cases", access: "all", group: "investigate", icon: "cases" },
  { href: "/console/search", label: "Search", access: "all", group: "investigate", icon: "search" },
  { href: "/console/vehicles", label: "Vehicles", access: "all", group: "investigate", icon: "vehicles" }, // CAP-06
  { href: "/console/graph", label: "Graph", access: "analyst+", group: "investigate", icon: "graph" },
  { href: "/console/alerts", label: "Link alerts", access: "all", group: "links", icon: "alerts" },
  { href: "/console/series", label: "Series", access: "all", group: "links", icon: "series" },
  { href: "/console/taskforces", label: "Task forces", access: "all", group: "links", icon: "taskforces" },
  { href: "/console/memory", label: "Memory", access: "analyst+", group: "links", icon: "memory" },
  { href: "/console/appeals", label: "Appeals", access: ["station_officer", "supervisor", "admin"], group: "public", icon: "appeals" },
  { href: "/console/tips", label: "Tips", access: ["station_officer", "analyst", "supervisor", "admin"], group: "public", icon: "tips" },
  { href: "/console/stations", label: "Stations", access: "supervisor+", group: "system", icon: "stations" },
  { href: "/console/system/sources", label: "Data sources", access: "admin", group: "system", icon: "sources" }, // WS3-27
  { href: "/console/system", label: "System", access: "admin", group: "system", icon: "system" },
  { href: "/console/admin", label: "Admin", access: "admin", group: "system", icon: "admin" },
];

export function navFor(role: Role | null | undefined): NavItem[] {
  return NAV.filter((n) => !n.hidden && allows(role, n.access));
}

/** Access rule for a console path (longest matching prefix in NAV); unknown paths need any police role. */
export function accessForPath(pathname: string): Access {
  if (pathname === "/console/cases/new") return ["station_officer", "admin"];
  // A run trace is analyst+; the page then hides tip and search runs from non-admins (trace.ts traceAccess).
  if (pathname.startsWith("/console/system/trace/")) return "analyst+";
  if (pathname.startsWith("/console/system")) return "admin";
  const hit = NAV.filter((n) => n.href !== "/console" && (pathname === n.href || pathname.startsWith(n.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return hit ? hit.access : "all";
}
