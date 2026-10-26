import Link from "next/link";
import type { ReactNode } from "react";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit } from "@/lib/alertsData";
import { CASE_STATUSES, CATEGORIES, humanise, listPlace } from "@/lib/cases";
import { stationOptions } from "@/lib/casesData";
import { hasCriteria, kindLabel, parseSearch, TIME_BANDS } from "@/lib/search";
import { runSearch } from "@/lib/searchData";
import { tagVariants } from "@/lib/similar";
import { fetchByTags, fetchSimilar } from "@/lib/similarData";
import { SimilarList } from "../cases/_components/SimilarList";
import { UntrustedText } from "@/components/console/tips/TipBits";

export const dynamic = "force-dynamic";

const input = "rounded-md border border-line bg-bg px-2 py-1.5 text-sm";

function fmt(at: string) {
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" });
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold">{title} <span className="font-mono text-xs text-muted">{count}</span></h2>
      <div className="mt-3 text-sm">{count === 0 ? <p className="text-muted">No matches.</p> : children}</div>
    </section>
  );
}

/** Spec G2 /console/search: one box (case id, FIR no, plate with ? wildcards, or words) plus facets. */
export default async function SearchPage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const officer = await requireOfficer("all");
  const p = parseSearch(searchParams);
  const sb = consoleServerClient();
  const stations = await stationOptions(sb);
  const names = Object.fromEntries(stations.map((s) => [s.station_id, s.name]));
  const zones = Array.from(new Set(stations.map((s) => s.zone).filter((z): z is string => !!z))).sort();
  const similar = p.similar ? await fetchSimilar(sb, p.similar, 50) : null;
  const res = !p.similar && hasCriteria(p) ? await runSearch(sb, p) : null;
  const tagHits = res && p.kind === "text" ? await fetchByTags(sb, tagVariants(p.value)) : null;
  if (res) await audit(sb, "search", "search", p.q || "(filters)", { kind: p.kind, facets: p.facets });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Search</h1>
        <p className="text-sm text-muted">
          One box for a case id, an FIR number (1182/2026), a vehicle plate (TN09??4471, ? = unread) or words from narratives, addresses, vehicles,
          persons and screened tips. Add filters to narrow it.
          {officer.role === "station_officer" ? " You see your own station's full cases; other stations appear through alerts and the map." : ""}
        </p>
      </div>

      <form method="get" className="space-y-3 rounded-xl border border-line bg-surface p-4" role="search">
        <div className="flex gap-2">
          <input name="q" defaultValue={p.q} autoFocus placeholder="red pulsar chain snatching · TN09??4471 · 1182/2026" className={`${input} flex-1 text-base`} aria-label="Search" />
          <button className="rounded-md bg-ink px-4 py-1.5 text-sm font-semibold text-bg">Search</button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {officer.role !== "station_officer" && (
            <select name="station" defaultValue={p.facets.station ?? ""} className={input} aria-label="Station">
              <option value="">All stations</option>
              {stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.name}</option>)}
            </select>
          )}
          <select name="category" defaultValue={p.facets.category ?? ""} className={input} aria-label="Category">
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{humanise(c)}</option>)}
          </select>
          <select name="status" defaultValue={p.facets.status ?? ""} className={input} aria-label="Status">
            <option value="">Any status</option>
            {CASE_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}
          </select>
          <input type="date" name="from" defaultValue={p.facets.from ?? ""} className={input} aria-label="Occurred from" />
          <input type="date" name="to" defaultValue={p.facets.to ?? ""} className={input} aria-label="Occurred to" />
          <select name="zone" defaultValue={p.facets.zone ?? ""} className={input} aria-label="Zone">
            <option value="">All zones</option>
            {zones.map((z) => <option key={z} value={z}>{z}</option>)}
          </select>
          <select name="tod" defaultValue={p.facets.tod ?? ""} className={input} aria-label="Time of day">
            <option value="">Any time of day</option>
            {TIME_BANDS.map((t) => <option key={t} value={t}>{humanise(t)}</option>)}
          </select>
          <input name="weapon" defaultValue={p.facets.weapon ?? ""} list="weapons" placeholder="weapon (knife, cutter…)" className={input} aria-label="Weapon" />
          <datalist id="weapons"><option value="knife" /><option value="cutter" /><option value="ligature" /></datalist>
          <input name="mo" defaultValue={p.facets.mo ?? ""} placeholder="MO or visual tag (two wheeler from behind)" className={input} aria-label="MO tag" />
          <select name="linked" defaultValue={p.facets.linked ?? ""} className={input} aria-label="Linked">
            <option value="">Linked or not</option>
            <option value="linked">In a link alert</option>
            <option value="unlinked">Not in any alert</option>
          </select>
        </div>
      </form>

      {!res && <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">Type something or pick a filter.</p>}

      {p.similar && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="text-lg font-semibold">Similar MO to <Link href={`/console/cases/${encodeURIComponent(p.similar)}`} className="font-mono text-signal hover:underline">{p.similar}</Link></h2>
          <div className="mt-3 text-sm">
            {similar ? <SimilarList hits={similar.hits} names={names} /> : <p className="text-muted">That case has no extracted MO or visual tags yet, so there is nothing to compare.</p>}
          </div>
        </section>
      )}

      {res && (
        <>
          {res.capped && <p className="text-xs text-muted">A tag or linked filter matched more than 500 cases; results use the first 500. Add another filter to narrow it.</p>}
          <Group title="Cases" count={res.cases.length}>
            <ul className="divide-y divide-line">
              {res.cases.map((c) => (
                <li key={c.crime_id} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                  <span>
                    <Link href={`/console/cases/${encodeURIComponent(c.crime_id)}`} className="font-semibold text-signal hover:underline">
                      {(names[c.station_id] ?? c.station_id).replace(/^PS-/, "")} {c.fir_no}
                    </Link>
                    <span className="text-muted"> · {humanise(c.category)}{c.sub_type ? ` · ${humanise(c.sub_type)}` : ""}{c.ward_no ? ` · ${listPlace(c.ward_no)}` : ""}</span>
                  </span>
                  <span className="text-xs text-muted">{fmt(c.occurred_from)} · <span className="font-mono">{c.crime_id}</span></span>
                </li>
              ))}
            </ul>
            {res.cases.length >= 50 && <p className="mt-2 text-xs text-muted">Showing the newest 50. Add a filter to narrow it.</p>}
          </Group>

          {(p.kind === "plate" || p.kind === "text") && (
            <Group title="Vehicles" count={res.vehicles.length}>
              <ul className="divide-y divide-line">
                {res.vehicles.slice(0, 50).map((v, i) => (
                  <li key={`${v.crime_id}-${i}`} className="py-1.5">
                    <span className="font-mono">{v.plate_pattern ?? "unread plate"}</span> · {[v.colour, v.make_model, humanise(v.vehicle_type)].filter(Boolean).join(" ")} · {humanise(v.role)} ·{" "}
                    <Link href={`/console/cases/${encodeURIComponent(v.crime_id)}`} className="text-signal hover:underline">{v.crime_id}</Link>
                  </li>
                ))}
              </ul>
            </Group>
          )}

          {p.kind === "text" && tagHits && (
            <Group title="Visual and MO tags" count={tagHits.rows.length}>
              <ul className="divide-y divide-line">
                {tagHits.rows.map((c) => (
                  <li key={c.crime_id} className="py-1.5">
                    <Link href={`/console/cases/${encodeURIComponent(c.crime_id)}`} className="font-mono text-signal hover:underline">{c.crime_id}</Link>
                    <span className="text-muted"> · {(names[c.station_id] ?? c.station_id).replace(/^PS-/, "")} · {humanise(c.category)}{c.week ? ` · ${c.week}` : ""}</span>
                    <span className="ml-2 inline-flex flex-wrap gap-1">{(c.visual_tags ?? []).concat(c.mo_tags ?? []).filter((t) => tagVariants(p.value).includes(t)).map((t) => <span key={t} className="rounded bg-signal-soft px-1.5 py-0.5 text-xs text-signal">{humanise(t)}</span>)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">Matches whole tags written by the Extractor (vision and text), e.g. &ldquo;black helmet&rdquo;, &ldquo;red motorcycle&rdquo;.</p>
            </Group>
          )}

          {p.kind === "text" && (
            <>
              <Group title="Persons" count={res.persons.length}>
                <ul className="space-y-1">
                  {res.persons.map((x) => <li key={x.person_id}><span className="font-mono text-xs">{x.person_id}</span> · {x.name ?? "unnamed"}{x.aliases.length ? ` · aka ${x.aliases.join(", ")}` : ""}</li>)}
                </ul>
              </Group>
              <Group title="Tips" count={res.tips.length}>
                <ul className="space-y-3">
                  {res.tips.map((t) => (
                    <li key={t.tip_id}>
                      <p className="mb-1 text-xs text-muted"><Link href={`/console/tips/${encodeURIComponent(t.tip_id)}`} className="text-signal hover:underline">{t.tip_id}</Link> · {humanise(t.category)} · {t.received_week} · {t.status}</p>
                      <UntrustedText text={t.text} clamp />
                    </li>
                  ))}
                </ul>
              </Group>
            </>
          )}

          <footer className="rounded-xl border border-line p-4 text-xs text-muted">
            <p>
              Read as <strong>{kindLabel(p.kind)}</strong>{p.kind !== "empty" && p.kind !== "text" ? ` (${p.value})` : p.words.length ? ` (${p.words.join(", ")})` : ""}.
              Sources queried (Supabase, under your role&apos;s row-level security):
            </p>
            <ul className="mt-1 flex flex-wrap gap-x-4">
              {tagHits && <li><span className="font-mono">crimes_citywide (tags)</span> → {tagHits.rows.length}{tagHits.error ? ` · error: ${tagHits.error}` : ""}</li>}
              {res.sources.map((s) => <li key={s.group}><span className="font-mono">{s.source}</span> → {s.rows}{s.error ? ` · error: ${s.error}` : ""}</li>)}
            </ul>
            <p className="mt-1">Agent-side searches (Scout Intent routing, similar-MO, ANPR, calls, news) run through Zetaris named queries on the local pipeline and are listed with their query ids in each run trace.</p>
          </footer>
        </>
      )}
    </div>
  );
}
