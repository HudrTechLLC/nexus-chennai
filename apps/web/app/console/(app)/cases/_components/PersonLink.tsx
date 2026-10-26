"use client";
import { useState, useTransition } from "react";
import { humanise } from "@/lib/cases";
import { DESCRIPTOR_KEYS, isNamedRole, PERSON_ROLES, type LinkForm, type PersonRole } from "@/lib/persons";
import { findPersons, linkPerson, type PersonOption } from "../[crimeId]/personActions";

const input = "rounded-md border border-line bg-bg px-2 py-1 text-sm";
const blank = (role: PersonRole = "suspect"): LinkForm => ({ role, personId: "", name: "", aliases: "", descriptors: {}, residenceWard: "" });

/** Link a known accused/suspect from the register, or add a described person (spec CAP-01, CAP-05). */
export function PersonLink({ crimeId }: { crimeId: string }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<LinkForm>(blank());
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<PersonOption[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  const named = isNamedRole(f.role);

  if (!open) {
    return (
      <div className="space-y-1">
        <button type="button" onClick={() => { setOpen(true); setMsg(null); }} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-bg">Link a person</button>
        {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm ${msg.ok ? "text-signal" : "text-red-600"}`}>{msg.text}</p>}
      </div>
    );
  }
  return (
    <form
      className="space-y-2 rounded-lg border border-dashed border-line p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await linkPerson(crimeId, f);
          if (r.ok) { setMsg({ ok: true, text: `Linked ${r.personId}.` }); setOpen(false); setF(blank()); setFound([]); setQuery(""); }
          else setMsg({ ok: false, text: r.error });
        });
      }}
    >
      <label className="flex items-center gap-2">Role
        <select value={f.role} onChange={(e) => setF({ ...blank(e.target.value as PersonRole) })} className={input}>
          {PERSON_ROLES.map((r) => <option key={r} value={r}>{humanise(r)}</option>)}
        </select>
      </label>

      {named && (
        <div className="space-y-1">
          <div className="flex gap-2">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find in the persons register (name or alias)" className={`${input} flex-1`} />
            <button type="button" onClick={() => start(async () => setFound(await findPersons(query)))} className="rounded-md border border-line px-2 py-1">Find</button>
          </div>
          {found.length > 0 && (
            <ul className="divide-y divide-line rounded-md border border-line">
              {found.map((p) => (
                <li key={p.person_id}>
                  <button type="button" onClick={() => setF({ ...f, personId: p.person_id })} className={`w-full px-2 py-1 text-left text-xs hover:bg-bg ${f.personId === p.person_id ? "bg-signal-soft" : ""}`}>
                    <span className="font-mono">{p.person_id}</span> · {p.name}{p.aliases.length ? ` · aka ${p.aliases.join(", ")}` : ""}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {f.personId && <p className="text-xs">Linking existing person <span className="font-mono">{f.personId}</span>. <button type="button" onClick={() => setF({ ...f, personId: "" })} className="underline">Add a new one instead</button></p>}
        </div>
      )}

      {!f.personId && (
        <>
          {named ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={120} placeholder="Name (if known)" className={input} />
              <input value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} placeholder="Aliases, comma-separated" className={input} />
            </div>
          ) : (
            <p className="text-xs text-muted">{humanise(f.role)}s are recorded by description only; no name is stored.</p>
          )}
          <div className="grid gap-2 sm:grid-cols-4">
            {DESCRIPTOR_KEYS.map((k) => (
              <input key={k} value={f.descriptors[k] ?? ""} maxLength={80} onChange={(e) => setF({ ...f, descriptors: { ...f.descriptors, [k]: e.target.value } })} placeholder={humanise(k)} className={input} aria-label={humanise(k)} />
            ))}
          </div>
          {named && <input value={f.residenceWard} inputMode="numeric" onChange={(e) => setF({ ...f, residenceWard: e.target.value })} placeholder="Residence ward (optional)" className={input} />}
        </>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button disabled={pending} className="rounded-md bg-ink px-3 py-1.5 font-semibold text-bg disabled:opacity-60">{pending ? "Linking…" : "Link to this case"}</button>
        <button type="button" onClick={() => { setOpen(false); setF(blank()); }} className="text-muted hover:text-ink">Cancel</button>
        {msg && !msg.ok && <p role="alert" className="text-red-600">{msg.text}</p>}
      </div>
    </form>
  );
}
