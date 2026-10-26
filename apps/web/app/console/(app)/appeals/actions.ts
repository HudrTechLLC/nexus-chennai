"use server";
import { revalidatePath } from "next/cache";
import { getOfficer } from "@/lib/auth";
import { allows } from "@/lib/roles";
import { caseTerms, isCrimeId, parseLookingFor, validateAppeal, type CaseTerm } from "@/lib/appeals";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit } from "@/lib/alertsData";

export type ActionResult = { ok: true } | { ok: false; error: string };

const WRITERS = ["station_officer", "supervisor", "admin"] as const;

async function writer() {
  const officer = await getOfficer();
  if (!officer) return { error: "Sign in again." } as const;
  if (!allows(officer.role, [...WRITERS])) return { error: "Your role can read appeals but not draft or publish them." } as const;
  return { officer } as const;
}

/** Ask the worker for a Sanitiser draft (appeal_requests; RLS: can_write_crime, requested_by = auth.uid()). */
export async function requestDraft(crimeId: string): Promise<ActionResult> {
  const w = await writer();
  if ("error" in w) return { ok: false, error: w.error as string };
  const id = crimeId.trim();
  if (!isCrimeId(id)) return { ok: false, error: "Enter a case id like CHN-AD-2026-001182." };
  const sb = consoleServerClient();
  const { error } = await sb.from("appeal_requests").insert({ crime_id: id, requested_by: w.officer.userId });
  if (error) return { ok: false, error: error.code === "42501" ? "You can only request appeals for your own station's cases." : error.message };
  await audit(sb, "request_appeal_draft", "crime", id);
  revalidatePath("/console/appeals");
  return { ok: true };
}

/**
 * Save edits, publish or withdraw. Updates public_incidents as the officer (RLS: can_write_crime); the publish
 * guard trigger (0006_02, 0007_08) blocks leaky published text and stamps approved_by from the officer's profile.
 */
export async function saveAppeal(
  id: string,
  input: { title: string; area_label: string; summary: string; looking_for: string; action: "save" | "publish" | "withdraw" },
): Promise<ActionResult> {
  const w = await writer();
  if ("error" in w) return { ok: false, error: w.error as string };
  const edit = {
    title: input.title.trim(), area_label: input.area_label.trim(), summary: input.summary.trim(), looking_for: parseLookingFor(input.looking_for),
  };
  const sb = consoleServerClient();
  if (input.action !== "withdraw") {
    const problem = validateAppeal(edit, await appealCaseTerms(sb, id));
    if (problem) return { ok: false, error: problem };
  }
  const values =
    input.action === "withdraw"
      ? { status: "withdrawn" }
      : { ...edit, ...(input.action === "publish" ? { status: "published" } : {}) };
  const { data, error } = await sb.from("public_incidents").update(values).eq("public_incident_id", id).select("public_incident_id, crime_id, status");
  if (error) return { ok: false, error: error.message };
  if (!data || data.length === 0) return { ok: false, error: "You can only edit appeals for your own station's cases." };
  // J4: publishing to the public is the most consequential console action, so every save is audited.
  await audit(sb, `appeal_${input.action}`, "public_incident", id, {
    crime_id: data[0].crime_id, status: data[0].status,
    ...(input.action === "withdraw" ? {} : { title: edit.title, looking_for: edit.looking_for.length }),
  });
  revalidatePath(`/console/appeals/${encodeURIComponent(id)}`);
  revalidatePath("/console/appeals");
  return { ok: true };
}

/**
 * Names of people linked to the appeal's case and its address (0007_08), read as the officer for an early,
 * readable error. If RLS hides any of them the database trigger still blocks the publish.
 */
async function appealCaseTerms(sb: ReturnType<typeof consoleServerClient>, id: string): Promise<CaseTerm[]> {
  const { data: pi } = await sb.from("public_incidents").select("crime_id").eq("public_incident_id", id).maybeSingle();
  const crimeId = (pi as { crime_id: string | null } | null)?.crime_id;
  if (!crimeId) return [];
  const [crime, links] = await Promise.all([
    sb.from("crimes").select("address").eq("crime_id", crimeId).maybeSingle(),
    sb.from("person_links").select("persons(name, aliases)").eq("crime_id", crimeId),
  ]);
  const persons = ((links.data ?? []) as unknown as { persons: { name: string | null; aliases: string[] | null } | null }[])
    .map((l) => l.persons)
    .filter((p): p is { name: string | null; aliases: string[] | null } => !!p);
  return caseTerms(persons, (crime.data as { address: string | null } | null)?.address);
}
