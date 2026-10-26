import "server-only";
import { redirect } from "next/navigation";
import { consoleServerClient } from "@/lib/supabase/server";
import { allows, isRole, type Access, type Role } from "@/lib/roles";

export type Officer = {
  userId: string;
  email: string;
  name: string;
  role: Role;
  stationId: string | null;
};

/** The signed-in officer, or null (no session, or a user with no police profile). */
export async function getOfficer(): Promise<Officer | null> {
  const sb = consoleServerClient();
  const { data: auth } = await sb.auth.getUser();
  if (!auth.user) return null;
  const { data } = await sb.from("profiles").select("name, role, station_id").eq("user_id", auth.user.id).maybeSingle();
  if (!data || !isRole(data.role)) return null;
  return { userId: auth.user.id, email: auth.user.email ?? "", name: data.name, role: data.role, stationId: data.station_id };
}

/** Page guard: sends a visitor without the right role to sign-in or to the "not allowed" notice. */
export async function requireOfficer(access: Access = "all"): Promise<Officer> {
  const officer = await getOfficer();
  if (!officer) redirect("/console/login");
  if (!allows(officer.role, access)) redirect("/console?denied=1");
  return officer;
}
