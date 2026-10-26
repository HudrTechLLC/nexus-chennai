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
 * `desktop`: where the item sits in the wide (md+) bar so it stays on one line at 1080p:
 * "bell" = left out, the header bell already links there; "manage" = under the Manage menu.
 * The phone menu always lists every item.
 */
export type NavItem = { href: string; label: string; access: Access; hidden?: boolean; desktop?: "bell" | "manage" };

/** Console navigation in G2 order. Items the role cannot open are hidden. */
export const NAV: NavItem[] = [
  { href: "/console", label: "Overview", access: "all" },
  { href: "/console/map", label: "Pulse Map", access: "all" },
  { href: "/console/alerts", label: "Link alerts", access: "all" },
  { href: "/console/cases", label: "Cases", access: "all" },
  { href: "/console/search", label: "Search", access: "all" },
  { href: "/console/vehicles", label: "Vehicles", access: "all" }, // CAP-06
  { href: "/console/series", label: "Series", access: "all" },
  { href: "/console/appeals", label: "Appeals", access: ["station_officer", "supervisor", "admin"] },
  { href: "/console/tips", label: "Tips", access: ["station_officer", "analyst", "supervisor", "admin"] },
  { href: "/console/graph", label: "Graph", access: "analyst+" },
  { href: "/console/stations", label: "Stations", access: "supervisor+", desktop: "manage" },
  { href: "/console/taskforces", label: "Task forces", access: "all" },
  { href: "/console/memory", label: "Memory", access: "analyst+" },
  { href: "/console/notifications", label: "Notifications", access: "all", desktop: "bell" },
  { href: "/console/system", label: "System", access: "admin", desktop: "manage" },
  { href: "/console/admin", label: "Admin", access: "admin", desktop: "manage" },
];

export function navFor(role: Role | null | undefined): NavItem[] {
  return NAV.filter((n) => !n.hidden && allows(role, n.access));
}

/** The wide-screen bar: inline links, and the ones grouped under "Manage" (empty = no menu). */
export function desktopNav(items: NavItem[]): { inline: NavItem[]; manage: NavItem[] } {
  return { inline: items.filter((n) => !n.desktop), manage: items.filter((n) => n.desktop === "manage") };
}

/** Access rule for a console path (longest matching prefix in NAV); unknown paths need any police role. */
export function accessForPath(pathname: string): Access {
  if (pathname === "/console/cases/new") return ["station_officer", "admin"];
  if (pathname.startsWith("/console/system")) return "admin";
  const hit = NAV.filter((n) => n.href !== "/console" && (pathname === n.href || pathname.startsWith(n.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return hit ? hit.access : "all";
}
