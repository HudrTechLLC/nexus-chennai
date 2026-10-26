"use client";
import { useMemo, useState, useTransition, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { CATEGORIES, CRIME_TYPES, humanise } from "@/lib/cases";
import {
  AGE_BANDS, BUILDS, emptyFir, GENDERS, LIMITS, VEHICLE_ROLES, VEHICLE_TYPES,
  type FirForm, type FirOffender, type FirProperty, type FirVehicle, type FirVictim,
} from "@/lib/fir";
import { fileFir, placeCheck, type PlaceResult } from "../new/actions";

const PlacePicker = dynamic(() => import("./PlacePicker"), {
  ssr: false,
  loading: () => <div className="grid h-72 place-items-center rounded-lg border border-line text-sm text-muted">Loading map…</div>,
});

export type SectionOption = { ipc_code: string | null; bns_code: string | null; title: string; category_group: string };

const input = "w-full rounded-md border border-line bg-bg px-2 py-1.5 text-sm";
const small = "rounded-md border border-line bg-bg px-2 py-1 text-sm";

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-xl border border-line bg-surface p-5">
      <legend className="px-1 text-lg font-semibold">{title}</legend>
      {hint && <p className="-mt-1 mb-3 text-xs text-muted">{hint}</p>}
      <div className="space-y-3">{children}</div>
    </fieldset>
  );
}

function Err({ msg }: { msg?: string }) {
  return msg ? <p role="alert" className="text-xs text-red-600">{msg}</p> : null;
}

/** Row editor for repeating groups (vehicles, offenders, victims, property). */
function Rows<T>({ rows, blank, max, label, onChange, render }: {
  rows: T[]; blank: T; max: number; label: string; onChange: (rows: T[]) => void; render: (row: T, set: (row: T) => void, i: number) => ReactNode;
}) {
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-start gap-2 rounded-lg border border-line p-2">
          {render(r, (next) => onChange(rows.map((x, j) => (j === i ? next : x))), i)}
          <button type="button" onClick={() => onChange(rows.filter((_, j) => j !== i))} className="ml-auto text-xs text-muted hover:text-red-600">Remove</button>
        </div>
      ))}
      {rows.length < max && (
        <button type="button" onClick={() => onChange([...rows, blank])} className="text-sm text-signal hover:underline">+ Add {label}</button>
      )}
    </div>
  );
}

const sectionCode = (s: SectionOption) => (s.bns_code ?? s.ipc_code) as string;

export function FirFormView({ sections, stations, ownStationId, isAdmin, home }: {
  sections: SectionOption[]; stations: { station_id: string; name: string }[]; ownStationId: string | null; isAdmin: boolean;
  home?: [number, number] | null;
}) {
  const [f, setF] = useState<FirForm>(emptyFir());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [filed, setFiled] = useState<string | null>(null);
  const [place, setPlace] = useState<PlaceResult | null>(null);
  const [secQuery, setSecQuery] = useState("");
  const [pending, start] = useTransition();
  const set = <K extends keyof FirForm>(k: K, v: FirForm[K]) => setF((prev) => ({ ...prev, [k]: v }));

  const byCode = useMemo(() => Object.fromEntries(sections.map((s) => [sectionCode(s), s])), [sections]);
  const suggested = useMemo(() => {
    const q = secQuery.trim().toLowerCase();
    return sections
      .filter((s) => (q ? `${s.bns_code ?? ""} ${s.ipc_code ?? ""} ${s.title}`.toLowerCase().includes(q) : s.category_group === f.category))
      .filter((s) => !f.sections.includes(sectionCode(s)))
      .slice(0, 8);
  }, [sections, secQuery, f.category, f.sections]);

  const station = isAdmin ? f.station_id ?? null : ownStationId;
  const outside = place?.stationId && station && place.stationId !== station;

  async function pick(lat: number, lon: number) {
    set("lat", lat);
    set("lon", lon);
    setPlace(await placeCheck(lat, lon));
  }

  function submit() {
    setMsg(null);
    start(async () => {
      const r = await fileFir(f);
      if (r.ok) {
        setFiled(r.crimeId);
        setErrors({});
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        setErrors(r.fields ?? {});
        setMsg(r.error);
      }
    });
  }

  if (filed) {
    return (
      <div role="status" className="rounded-xl border border-signal bg-signal-soft p-6">
        <p className="font-mono text-xs uppercase tracking-widest text-signal">FIR registered</p>
        <h2 className="mt-1 text-xl font-bold">{filed}</h2>
        <p className="mt-2 text-sm">
          The case is saved. The local pipeline picks it up on its next pass (usually within a minute): the Extractor reads the narrative and
          statements, then the Linker and Skeptic check it against other cases. The case file shows the extracted MO, any link alerts and the run trace.
        </p>
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <Link href={`/console/cases/${encodeURIComponent(filed)}`} className="rounded-md bg-ink px-3 py-2 font-semibold text-bg">Open the case file (processing)</Link>
          <Link href={`/console/cases/${encodeURIComponent(filed)}#evidence`} className="rounded-md border border-line px-3 py-2">Add evidence</Link>
          <button type="button" onClick={() => { setFiled(null); setF(emptyFir()); setPlace(null); }} className="rounded-md border border-line px-3 py-2">File another</button>
        </div>
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
      <Section title="Incident">
        {isAdmin && (
          <label className="block text-sm">Station
            <select value={f.station_id ?? ""} onChange={(e) => set("station_id", e.target.value || undefined)} className={input}>
              <option value="">Choose the station</option>
              {stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.name}</option>)}
            </select>
            <Err msg={errors.station_id} />
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">Category
            <select value={f.category} onChange={(e) => setF((p) => ({ ...p, category: e.target.value, sub_type: "" }))} className={input}>
              <option value="">Choose…</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{humanise(c)}</option>)}
            </select>
            <Err msg={errors.category} />
          </label>
          <label className="text-sm">Sub-type
            <select value={f.sub_type} onChange={(e) => set("sub_type", e.target.value)} className={input} disabled={!f.category}>
              <option value="">—</option>
              {(CRIME_TYPES[f.category] ?? []).map((s) => <option key={s} value={s}>{humanise(s)}</option>)}
            </select>
            <Err msg={errors.sub_type} />
          </label>
          <label className="text-sm">Severity (1 minor – 5 grave)
            <input type="number" min={1} max={5} value={f.severity} onChange={(e) => set("severity", Number(e.target.value))} className={input} />
            <Err msg={errors.severity} />
          </label>
        </div>

        <div className="text-sm">
          <p>Sections (BNS, with IPC equivalent)</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {f.sections.map((c) => (
              <span key={c} className="inline-flex items-center gap-1 rounded bg-bg px-2 py-0.5 text-xs">
                {c}{byCode[c]?.ipc_code && byCode[c]?.bns_code ? ` ↔ ${byCode[c].ipc_code}` : ""} · {byCode[c]?.title}
                <button type="button" aria-label={`Remove ${c}`} onClick={() => set("sections", f.sections.filter((x) => x !== c))} className="text-muted hover:text-red-600">×</button>
              </span>
            ))}
          </div>
          <input value={secQuery} onChange={(e) => setSecQuery(e.target.value)} placeholder="Type an IPC or BNS code or a word (e.g. IPC 392, snatching)" className={`${input} mt-2`} />
          <ul className="mt-1 divide-y divide-line rounded-md border border-line">
            {suggested.map((s) => (
              <li key={sectionCode(s)}>
                <button type="button" onClick={() => { set("sections", [...f.sections, sectionCode(s)]); setSecQuery(""); }} className="w-full px-2 py-1 text-left text-xs hover:bg-bg">
                  <span className="font-mono">{s.bns_code ?? "—"}</span>{s.ipc_code ? <span className="text-muted"> (was {s.ipc_code})</span> : null} · {s.title}
                </button>
              </li>
            ))}
            {suggested.length === 0 && <li className="px-2 py-1 text-xs text-muted">{f.category || secQuery ? "No matching section." : "Choose a category or type a code."}</li>}
          </ul>
          <Err msg={errors.sections} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Occurred from
            <input type="datetime-local" value={f.occurred_from} onChange={(e) => set("occurred_from", e.target.value)} className={input} />
            <Err msg={errors.occurred_from} />
          </label>
          <label className="text-sm">Occurred to (optional)
            <input type="datetime-local" value={f.occurred_to} onChange={(e) => set("occurred_to", e.target.value)} className={input} />
            <Err msg={errors.occurred_to} />
          </label>
        </div>
        <p className="text-xs text-muted">Reported at: now, when you save. Times are city time.</p>
      </Section>

      <Section title="Place" hint="Click the scene on the map. The ward and police station are looked up from their boundaries.">
        <PlacePicker lat={f.lat} lon={f.lon} onPick={pick} home={home} />
        <Err msg={errors.place} />
        {f.lat !== null && (
          <p className="text-xs text-muted">
            {f.lat}, {f.lon}{place?.wardName ? ` · ${place.wardName}` : ""}{place?.stationName ? ` · ${place.stationName} jurisdiction` : " · outside every station boundary"}
          </p>
        )}
        {outside && (
          <p role="alert" className="rounded-md border border-amber-400 px-3 py-2 text-sm text-amber-700">
            This place is in {place?.stationName}&apos;s jurisdiction, not yours. You can still register it (zero FIR) and transfer it later.
          </p>
        )}
        <label className="block text-sm">Address or landmark
          <input value={f.address} maxLength={LIMITS.address} onChange={(e) => set("address", e.target.value)} placeholder="near a bus stop, LB Road" className={input} />
          <Err msg={errors.address} />
        </label>
      </Section>

      <Section title="People" hint="The complainant's name is not stored here; victims and offenders are described, not named.">
        <p className="text-sm font-medium">Victims</p>
        <Rows<FirVictim> rows={f.victims} blank={{ gender: "", age_band: "" }} max={LIMITS.people} label="victim" onChange={(v) => set("victims", v)}
          render={(r, s) => (
            <>
              <select value={r.gender} onChange={(e) => s({ ...r, gender: e.target.value })} className={small} aria-label="Gender"><option value="">Gender</option>{GENDERS.map((g) => <option key={g}>{g}</option>)}</select>
              <select value={r.age_band} onChange={(e) => s({ ...r, age_band: e.target.value })} className={small} aria-label="Age band"><option value="">Age</option>{AGE_BANDS.map((a) => <option key={a}>{a}</option>)}</select>
            </>
          )} />
        <p className="pt-2 text-sm font-medium">Described offenders</p>
        <Rows<FirOffender> rows={f.offenders} blank={{ count: "1", build: "", age_band: "", helmet: "", clothing: "", marks: "" }} max={LIMITS.people} label="offender description" onChange={(v) => set("offenders", v)}
          render={(r, s) => (
            <>
              <input type="number" min={1} max={20} value={r.count} onChange={(e) => s({ ...r, count: e.target.value })} className={`${small} w-16`} aria-label="How many" />
              <select value={r.build} onChange={(e) => s({ ...r, build: e.target.value })} className={small} aria-label="Build"><option value="">Build</option>{BUILDS.map((b) => <option key={b}>{b}</option>)}</select>
              <select value={r.age_band} onChange={(e) => s({ ...r, age_band: e.target.value })} className={small} aria-label="Age band"><option value="">Age</option>{AGE_BANDS.map((a) => <option key={a}>{a}</option>)}</select>
              <input value={r.helmet} onChange={(e) => s({ ...r, helmet: e.target.value })} placeholder="helmet" className={small} />
              <input value={r.clothing} onChange={(e) => s({ ...r, clothing: e.target.value })} placeholder="clothing" className={small} />
              <input value={r.marks} onChange={(e) => s({ ...r, marks: e.target.value })} placeholder="marks" className={small} />
            </>
          )} />
        <Err msg={errors.people} />
      </Section>

      <Section title="Property and weapon">
        <Rows<FirProperty> rows={f.property} blank={{ item: "", value_inr: "" }} max={LIMITS.people} label="property item" onChange={(v) => set("property", v)}
          render={(r, s, i) => (
            <>
              <input value={r.item} onChange={(e) => s({ ...r, item: e.target.value })} placeholder="gold chain" className={small} />
              <input value={r.value_inr} inputMode="numeric" onChange={(e) => s({ ...r, value_inr: e.target.value })} placeholder="value ₹" className={`${small} w-28`} />
              <Err msg={errors[`property.${i}`]} />
            </>
          )} />
        <label className="block text-sm">Weapon or tool (optional)
          <input value={f.weapon} onChange={(e) => set("weapon", e.target.value)} placeholder="knife, cutter…" className={input} />
        </label>
      </Section>

      <Section title="Vehicles" hint="Write unread plate characters as ?, e.g. TN09??4471.">
        <Rows<FirVehicle> rows={f.vehicles} blank={{ role: "used_by_offender", vehicle_type: "motorcycle", plate_pattern: "", make_model: "", colour: "" }} max={LIMITS.vehicles} label="vehicle" onChange={(v) => set("vehicles", v)}
          render={(r, s, i) => (
            <>
              <select value={r.role} onChange={(e) => s({ ...r, role: e.target.value })} className={small} aria-label="Role">{VEHICLE_ROLES.map((x) => <option key={x} value={x}>{humanise(x)}</option>)}</select>
              <select value={r.vehicle_type} onChange={(e) => s({ ...r, vehicle_type: e.target.value })} className={small} aria-label="Type">{VEHICLE_TYPES.map((x) => <option key={x} value={x}>{humanise(x)}</option>)}</select>
              <input value={r.plate_pattern} onChange={(e) => s({ ...r, plate_pattern: e.target.value })} placeholder="TN09??4471" className={`${small} font-mono`} />
              <input value={r.make_model} onChange={(e) => s({ ...r, make_model: e.target.value })} placeholder="make / model" className={small} />
              <input value={r.colour} onChange={(e) => s({ ...r, colour: e.target.value })} placeholder="colour" className={`${small} w-24`} />
              <Err msg={errors[`vehicles.${i}`]} />
            </>
          )} />
        <Err msg={errors.vehicles} />
      </Section>

      <Section title="Narrative" hint="MO extraction runs after you save: the Extractor (Nemotron via Nightshift) reads this text on the local pipeline, and you review its result on the case file.">
        <textarea value={f.narrative} maxLength={LIMITS.narrative} onChange={(e) => set("narrative", e.target.value)} rows={7} className={input}
          placeholder="On <date> at about <time>, the complainant was at … Two unknown persons on a red motorcycle …" />
        <p className="text-right text-xs text-muted">{f.narrative.length}/{LIMITS.narrative}</p>
        <Err msg={errors.narrative} />
      </Section>

      <Section title="Statements" hint="Typed statements are saved with the FIR; witnesses are stored as masked references. Audio statements and evidence files are added on the case file after saving.">
        <Rows<string> rows={f.statements} blank="" max={LIMITS.statements} label="statement" onChange={(v) => set("statements", v)}
          render={(r, s, i) => (
            <label className="w-full text-xs text-muted">Witness {i + 1}
              <textarea value={r} maxLength={LIMITS.statement} onChange={(e) => s(e.target.value)} rows={3} className={input} />
            </label>
          )} />
        <Err msg={errors.statements} />
      </Section>

      <div className="flex flex-wrap items-center gap-3">
        <button disabled={pending} className="rounded-md bg-ink px-4 py-2 font-semibold text-bg disabled:opacity-60">{pending ? "Filing…" : "Save and register FIR"}</button>
        <Link href="/console/cases" className="text-sm text-muted hover:text-ink">Cancel</Link>
        {msg && <p role="alert" className="text-sm text-red-600">{msg}</p>}
      </div>
    </form>
  );
}
