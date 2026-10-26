/**
 * Persons on a case (spec CAP-01 known accused/suspects, CAP-05 persons register; 0007_04 link_person).
 * Pure helpers shared by the case file, the link form and the tests.
 */

export const PERSON_ROLES = ["accused", "suspect", "victim", "witness", "complainant"] as const;
export type PersonRole = (typeof PERSON_ROLES)[number];

/** Only these roles may carry a name or aliases; the others are described, never named (J5, B9). */
export const NAMED_ROLES: PersonRole[] = ["accused", "suspect"];

/** Descriptor keys the RPC accepts (same list as link_person). */
/** No complexion: a skin-colour proxy for community (LNK-13, 0007_05). */
export const DESCRIPTOR_KEYS = ["height_band", "build", "age_band", "gender", "marks", "clothing", "hair"] as const;
export type DescriptorKey = (typeof DESCRIPTOR_KEYS)[number];

export type LinkForm = {
  role: PersonRole;
  personId: string; // existing person, or "" to create one
  name: string;
  aliases: string; // comma-separated
  descriptors: Partial<Record<DescriptorKey, string>>;
  residenceWard: string;
};

export function isNamedRole(role: string): boolean {
  return (NAMED_ROLES as string[]).includes(role);
}

/** Null when the link can be sent, else the reason. Mirrors the RPC's checks so the officer sees them first. */
export function validateLink(f: LinkForm): string | null {
  if (!(PERSON_ROLES as readonly string[]).includes(f.role)) return "Choose a role.";
  const aliases = splitAliases(f.aliases);
  if (!isNamedRole(f.role) && (f.name.trim() || aliases.length)) return "Victims, witnesses and complainants are described, not named.";
  if (f.name.length > 120) return "Name is too long.";
  if (aliases.length > 10) return "At most 10 aliases.";
  if (Object.values(f.descriptors).some((v) => (v ?? "").length > 80)) return "Keep each descriptor under 80 characters.";
  if (f.residenceWard && !/^\d{1,4}$/.test(f.residenceWard)) return "Ward is a number.";
  if (!f.personId && !f.name.trim() && !Object.values(f.descriptors).some((v) => (v ?? "").trim())) return "Give a name (accused or suspect) or at least one descriptor.";
  return null;
}

export function splitAliases(text: string): string[] {
  return text.split(",").map((a) => a.trim()).filter(Boolean);
}

/** The jsonb link_person takes. */
export function toLinkPayload(crimeId: string, f: LinkForm) {
  const descriptors = Object.fromEntries(
    Object.entries(f.descriptors).map(([k, v]) => [k, (v ?? "").trim()]).filter(([, v]) => v),
  );
  return f.personId
    ? { crime_id: crimeId, role: f.role, person_id: f.personId }
    : {
        crime_id: crimeId, role: f.role, descriptors,
        ...(isNamedRole(f.role) ? { name: f.name.trim() || null, aliases: splitAliases(f.aliases) } : {}),
        ...(f.residenceWard ? { residence_ward: Number(f.residenceWard) } : {}),
      };
}

/**
 * What the case file shows for a linked person. Names and aliases appear only for accused and suspects;
 * any other role shows "(masked)" even if the register row has a name (J5).
 */
export function personLabel(role: string, person: { name: string | null; aliases: string[] } | null): string {
  if (!isNamedRole(role)) return "(identity masked)";
  if (!person) return "unknown";
  const name = person.name ?? "unnamed";
  return person.aliases?.length ? `${name} · aka ${person.aliases.join(", ")}` : name;
}
