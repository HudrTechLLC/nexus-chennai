"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { toLinkPayload, validateLink, type LinkForm } from "@/lib/persons";
import { consoleServerClient } from "@/lib/supabase/server";

export type LinkResult = { ok: true; personId: string } | { ok: false; error: string };
export type PersonOption = { person_id: string; name: string | null; aliases: string[]; descriptors: Record<string, unknown> };

/** Links a known or described person to a case through link_person (0007_04): can_write_crime, audited. */
export async function linkPerson(crimeId: string, form: LinkForm): Promise<LinkResult> {
  const officer = await getOfficer();
  if (!officer) return { ok: false, error: "Sign in again." };
  const problem = validateLink(form);
  if (problem) return { ok: false, error: problem };
  const { data, error } = await consoleServerClient().rpc("link_person", { p: toLinkPayload(crimeId, form) });
  if (error) return { ok: false, error: error.code === "42501" ? "Only the case's station (or a supervisor) can link people to it." : error.message };
  revalidatePath(`/console/cases/${encodeURIComponent(crimeId)}`);
  return { ok: true, personId: data as string };
}

/** Persons register lookup by name or alias, for linking an accused or suspect who is already known. */
export async function findPersons(text: string): Promise<PersonOption[]> {
  const officer = await getOfficer();
  const q = text.trim().replace(/[%_,()"'\*]/g, " ").trim();
  if (!officer || q.length < 2) return [];
  const { data } = await consoleServerClient().from("persons").select("person_id, name, aliases, descriptors")
    .or(`name.ilike.%${q}%,aliases.cs.{"${q}"}`).not("name", "is", null).limit(10);
  return (data ?? []) as PersonOption[];
}
