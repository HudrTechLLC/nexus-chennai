import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit, crimeTitle, officerNames, stationNames } from "@/lib/alertsData";
import { briefsChunked } from "@/lib/seriesData";
import { fetchTaskforce, officerDirectory } from "@/lib/taskforcesData";
import { abilities, sortMembers, stationsSpanned } from "@/lib/taskforces";
import { TfStatusPill } from "@/components/console/taskforces/TfBits";
import { DecidePanel, LinkCasesForm, MemberControls, MemberManager, NoteForm } from "@/components/console/taskforces/TaskforceForms";

export const dynamic = "force-dynamic";

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) : "—");
const card = "rounded-xl border border-line bg-surface p-5";

export default async function TaskforceDetail({ params }: { params: { taskforceId: string } }) {
  const officer = await requireOfficer("all");
  const id = decodeURIComponent(params.taskforceId);
  const sb = consoleServerClient();
  const { taskforce: tf, members, cases, notes } = await fetchTaskforce(sb, id);
  if (!tf) notFound();

  const people = [...members.map((m) => m.user_id), ...notes.map((n) => n.author), tf.created_by, tf.decided_by].filter((x): x is string => !!x);
  const [names, briefs] = await Promise.all([officerNames(sb, people), briefsChunked(sb, cases.map((c) => c.crime_id)), audit(sb, "view", "taskforce", id)]);
  const mine = members.find((m) => m.user_id === officer.userId)?.role ?? null;
  const can = abilities(officer.role, tf.status, mine);
  const directory = can.manageMembers ? await officerDirectory(sb) : [];
  const spanned = stationsSpanned(Object.values(briefs));
  const stNames = await stationNames(sb, spanned);
  const memberRows = sortMembers(members.map((m) => ({ ...m, name: names[m.user_id] ?? m.user_id.slice(0, 8) })));

  return (
    <div className="space-y-5">
      <div>
        <Link href="/console/taskforces" className="text-sm text-muted hover:text-ink">← Task forces</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">{tf.name}</h1>
          <TfStatusPill status={tf.status} />
          {tf.synthetic && <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">synthetic</span>}
        </div>
        <p className="mt-1 text-sm text-muted">
          <span className="font-mono text-xs">{tf.taskforce_id}</span>
          {" "}· proposed {fmt(tf.created_at)}{tf.created_by && names[tf.created_by] ? ` by ${names[tf.created_by]}` : ""}
          {tf.decided_at && <> · {tf.status === "declined" ? "declined" : "approved"} {fmt(tf.decided_at)}{tf.decided_by && names[tf.decided_by] ? ` by ${names[tf.decided_by]}` : ""}</>}
          {tf.closed_at && <> · closed {fmt(tf.closed_at)}</>}
        </p>
        <p className="mt-1 text-sm">
          {tf.series_id && <>Series <Link href={`/console/series/${encodeURIComponent(tf.series_id)}`} className="font-mono text-xs text-signal hover:underline">{tf.series_id}</Link> · </>}
          {tf.alert_id && <>Alert <Link href={`/console/alerts/${encodeURIComponent(tf.alert_id)}`} className="font-mono text-xs text-signal hover:underline">{tf.alert_id}</Link> · </>}
          {spanned.length} station{spanned.length === 1 ? "" : "s"}{spanned.length > 0 && <>: {spanned.map((s) => (stNames[s] ?? s).replace(/^PS-/, "")).join(", ")}</>}
        </p>
        {tf.purpose && <p className="mt-2 max-w-prose">{tf.purpose}</p>}
      </div>

      {(can.approve || can.close) && (
        <section className={`${card} border-accent`} aria-labelledby="decide">
          <h2 id="decide" className="mb-2 font-semibold">{can.approve ? "Supervisor decision" : "Close this task force"}</h2>
          <DecidePanel id={tf.taskforce_id} status={can.approve ? "proposed" : "active"} />
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className={card} aria-labelledby="members">
          <h2 id="members" className="font-semibold">Members <span className="text-sm font-normal text-muted">· {members.length}</span></h2>
          {memberRows.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No members yet. A supervisor adds officers from each station involved.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {memberRows.map((m) => (
                <li key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-sm">
                  <span>{m.name}{m.role === "lead" && <span className="ml-2 rounded-full bg-signal-soft px-2 py-0.5 text-xs text-signal">Lead</span>}{m.user_id === officer.userId && <span className="ml-2 text-xs text-muted">(you)</span>}</span>
                  {can.manageMembers && <MemberControls id={tf.taskforce_id} userId={m.user_id} role={m.role} />}
                </li>
              ))}
            </ul>
          )}
          {can.manageMembers && <div className="mt-3 border-t border-line pt-3"><MemberManager id={tf.taskforce_id} directory={directory} current={members} /></div>}
        </section>

        <section className={card} aria-labelledby="cases">
          <h2 id="cases" className="font-semibold">Linked cases <span className="text-sm font-normal text-muted">· {cases.length}</span></h2>
          {cases.length === 0 ? (
            <p className="mt-2 text-sm text-muted">No cases linked yet.{can.linkCases ? " Add case ids below." : ""}</p>
          ) : (
            <ul className="mt-2 max-h-80 divide-y divide-line overflow-auto">
              {cases.map((c) => {
                const b = briefs[c.crime_id];
                return (
                  <li key={c.crime_id} className="flex flex-wrap items-baseline justify-between gap-2 py-1.5 text-sm">
                    {b?.full
                      ? <Link href={`/console/cases/${encodeURIComponent(c.crime_id)}`} className="text-signal hover:underline">{crimeTitle(b, c.crime_id)}</Link>
                      : <span>{crimeTitle(b, c.crime_id)}</span>}
                    <span className="text-xs text-muted">{b ? `${b.category.replace(/_/g, " ")}${b.full ? "" : " · city-wide summary"}` : "not visible"}</span>
                  </li>
                );
              })}
            </ul>
          )}
          {can.linkCases && <div className="mt-3 border-t border-line pt-3"><LinkCasesForm id={tf.taskforce_id} /></div>}
        </section>
      </div>

      <section className={card} aria-labelledby="notes">
        <h2 id="notes" className="font-semibold">Notes <span className="text-sm font-normal text-muted">· permanent record, never edited or deleted</span></h2>
        {notes.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No notes yet.{can.addNote ? "" : " Members and supervisors add notes."}</p>
        ) : (
          <ol className="mt-2 space-y-3">
            {notes.map((n) => (
              <li key={n.note_id} className="text-sm">
                <p className="text-xs text-muted">
                  <b className="text-ink">{names[n.author] ?? n.author.slice(0, 8)}</b> · {fmt(n.at)}
                  {n.kind === "decision" && <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-accent">decision</span>}
                </p>
                <p className="mt-0.5 whitespace-pre-wrap">{n.text}</p>
              </li>
            ))}
          </ol>
        )}
        {can.addNote && <div className="mt-3 border-t border-line pt-3"><NoteForm id={tf.taskforce_id} /></div>}
      </section>
    </div>
  );
}
