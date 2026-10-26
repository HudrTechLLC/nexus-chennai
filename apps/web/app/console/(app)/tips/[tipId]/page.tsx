import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit, officerNames } from "@/lib/alertsData";
import { TIP_CATEGORY_LABEL, tipAreaLabel, type TipRow } from "@/lib/tips";
import { GuardBadges, UntrustedText } from "@/components/console/tips/TipBits";
import { ReplyForm, ReviewForm, type Nearby } from "@/components/console/tips/TipActions";
import { cellAreaLabel, consoleCell, consoleCellMapHref, consoleCrimeMapHref, tipLinkedCrimes, type TipCrimeSource } from "@/lib/consoleArea";

const SOURCE_LABEL: Record<TipCrimeSource, string> = { appeal: "appeal case", tip: "chosen by the tipster", review: "linked in a review" };

export const dynamic = "force-dynamic";

export default async function TipDetail({ params }: { params: { tipId: string } }) {
  await requireOfficer("all");
  const sb = consoleServerClient();
  const tipId = decodeURIComponent(params.tipId);
  const { data } = await sb.from("tips").select("*, tip_media(*), tip_reviews(*)").eq("tip_id", tipId).maybeSingle();
  if (!data) notFound();
  const tip = data as TipRow;
  await audit(sb, "view_tip", "tip", tipId);

  const [{ data: messages }, { data: nearby }, appeal] = await Promise.all([
    sb.from("tip_messages").select("message_id, sender, text, at").eq("tip_id", tipId).order("message_id"),
    sb.rpc("tip_nearby_crimes", { p_tip_id: tipId }),
    tip.public_incident_id
      ? sb.from("public_incidents").select("public_incident_id, title, crime_id").eq("public_incident_id", tip.public_incident_id).maybeSingle()
      : Promise.resolve({ data: null }),
  ]);
  const media = tip.tip_media ?? [];
  const { data: signed } = media.length
    ? await sb.storage.from("tip-media").createSignedUrls(media.map((m) => m.path), 600)
    : { data: [] as { signedUrl: string }[] };
  const reviews = [...(tip.tip_reviews ?? [])].sort((a, b) => b.at.localeCompare(a.at));
  const names = await officerNames(sb, reviews.map((r) => r.by));

  // WS3-24: the console map, framed on the tip's area and on each crime it is tied to. A crime link is offered
  // only when this officer may read the crime (can_read_crime, as the map's RLS would decide); never in a public URL.
  const mapCell = consoleCell(tip.approx_cell_fine) ?? consoleCell(tip.approx_cell);
  const linked = tipLinkedCrimes({ appealCrimeId: appeal.data?.crime_id, aboutCrimeId: tip.about_crime_id, reviews });
  const readable = await Promise.all(linked.map(async (l) => {
    const { data: ok } = await sb.rpc("can_read_crime", { p_crime_id: l.crimeId });
    return ok === true;
  }));
  // Crimes this officer may not read are counted, never named (no id on the page).
  const hidden = readable.filter((r) => !r).length;

  return (
    <div className="space-y-5">
      <Link href="/console/tips" className="text-sm text-muted hover:text-ink">← Tips</Link>
      <header className="space-y-2 rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="font-mono text-xl font-bold">{tip.tip_id}</h1>
          <span className="text-sm text-muted">
            {TIP_CATEGORY_LABEL[tip.category] ?? tip.category} · week {tip.received_week} · {tip.channel} · status {tip.status}
            {` · ${tipAreaLabel(tip)}`}
          </span>
        </div>
        <GuardBadges guard={tip.guard} status={tip.status} />
        {appeal.data && <p className="text-sm">Appeal: <strong>{appeal.data.title}</strong></p>}
        {(mapCell || linked.length > 0) && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" data-testid="tip-map-links">
            {mapCell && (
              <span>
                <Link href={consoleCellMapHref(mapCell)!} className="font-medium text-signal hover:underline">View on map</Link>
                <span className="text-xs text-muted"> · {cellAreaLabel(mapCell)}</span>
              </span>
            )}
            {linked.map((l, i) => readable[i] && (
              <span key={l.crimeId} className="text-xs">
                <span className="font-mono">{l.crimeId}</span> <span className="text-muted">({SOURCE_LABEL[l.source]})</span>{" "}
                <Link href={consoleCrimeMapHref(l.crimeId)!} className="font-medium text-signal hover:underline">See crime on map</Link>
              </span>
            ))}
            {hidden > 0 && (
              <span className="text-xs text-muted">
                {hidden === 1 ? "1 linked crime is" : `${hidden} linked crimes are`} not visible to your role
              </span>
            )}
          </div>
        )}
        {tip.status === "quarantined" && (
          <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
            Quarantined by Tip Guard: it is shown here for review but is never passed to the agents.
          </p>
        )}
        <UntrustedText text={tip.text} />
      </header>

      {media.length > 0 && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="font-semibold">Files</h2>
          <ul className="mt-2 grid gap-3 sm:grid-cols-3">
            {media.map((m, i) => (
              <li key={m.media_id} className="text-xs">
                {m.kind === "image" && signed?.[i]?.signedUrl
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={signed[i].signedUrl} alt={`Tip file ${i + 1}`} className="h-36 w-full rounded object-cover" />
                  : m.kind === "audio" && signed?.[i]?.signedUrl
                    ? <audio controls src={signed[i].signedUrl} className="w-full" />
                    : <div className="grid h-36 place-items-center rounded bg-bg">{m.kind}</div>}
                <p className="mt-1 text-muted">metadata removed{m.faces_blurred ? " · faces blurred" : ""}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3 rounded-xl border border-line bg-surface p-5">
          <h2 className="font-semibold">Suggested cases</h2>
          <p className="text-xs text-muted">The appeal&apos;s case, then cases in the same area from two weeks before to three weeks after the tip arrived. You see only cases your role may read.</p>
          {((nearby as Nearby[] | null) ?? []).length === 0 && <p className="text-sm text-muted">None found.</p>}
          <ul className="space-y-1 text-sm">
            {((nearby as Nearby[] | null) ?? []).map((n) => (
              <li key={n.crime_id}>
                <Link href={`/console/cases/${encodeURIComponent(n.crime_id)}`} className="font-mono text-xs text-signal hover:underline">{n.station_id.replace(/^PS-/, "")} {n.fir_no}</Link>{" "}
                <span className="text-muted">{n.sub_type?.replaceAll("_", " ") ?? n.category} · {new Date(n.occurred_from).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}{n.from_appeal ? " · appeal case" : ""}</span>
              </li>
            ))}
          </ul>
          <ReviewForm tipId={tip.tip_id} nearby={(nearby as Nearby[] | null) ?? []} />
          {reviews.length > 0 && (
            <ul className="space-y-1 border-t border-line pt-2 text-xs text-muted">
              {reviews.map((r) => (
                <li key={r.review_id}>{new Date(r.at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} · {names[r.by] ?? "officer"} · {r.useful ? "useful" : "not useful"}{r.crime_id ? ` · linked ${r.crime_id}` : ""}{r.note ? ` · ${r.note}` : ""}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-3 rounded-xl border border-line bg-surface p-5">
          <h2 className="font-semibold">Conversation</h2>
          <ol className="space-y-2">
            {(messages ?? []).length === 0 && <li className="text-sm text-muted">No messages.</li>}
            {(messages ?? []).map((m) => (
              <li key={m.message_id} className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${m.sender === "police" ? "ml-auto bg-signal-soft" : "bg-bg"}`}>
                <p className="text-xs text-muted">{m.sender === "police" ? "Police" : "Tipster (untrusted)"} · {String(m.at).slice(0, 10)}</p>
                <p className="whitespace-pre-wrap break-words">{m.text}</p>
              </li>
            ))}
          </ol>
          <ReplyForm tipId={tip.tip_id} followUp={tip.follow_up_enabled} />
        </div>
      </section>
    </div>
  );
}
