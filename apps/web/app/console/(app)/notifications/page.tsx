import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { CHANNEL_LABEL, kindLabel, parseShow, unreadCount, type AppNotification, type OutboxRow } from "@/lib/notifications";
import { markAllRead, openNotification } from "./actions";

export const dynamic = "force-dynamic";

function fmt(at: string) {
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** /console/notifications: in-app list (NOT-01) and the mock email / WhatsApp outbox (NOT-02). */
export default async function NotificationsPage({ searchParams }: { searchParams: { show?: string; outbox?: string } }) {
  const officer = await requireOfficer("all");
  const show = parseShow(searchParams.show);
  const allOutbox = officer.role === "admin" && searchParams.outbox === "all";
  const sb = consoleServerClient();

  let nq = sb.from("notifications").select("notification_id, user_id, kind, title, body, link, read_at, created_at")
    .eq("user_id", officer.userId).order("created_at", { ascending: false }).limit(100);
  if (show === "unread") nq = nq.is("read_at", null);
  let oq = sb.from("outbox").select("outbox_id, channel, recipient, payload, status, created_at, user_id")
    .order("created_at", { ascending: false }).limit(50);
  if (!allOutbox) oq = oq.eq("user_id", officer.userId);
  const [{ data: nRows, error: nErr }, { data: oRows, error: oErr }, { count: unread }] = await Promise.all([
    nq, oq,
    sb.from("notifications").select("notification_id", { count: "exact", head: true }).eq("user_id", officer.userId).is("read_at", null),
  ]);
  const list = (nRows ?? []) as AppNotification[];
  const outbox = (oRows ?? []) as OutboxRow[];
  const qs = (s: string, o = allOutbox ? "all" : "") => `/console/notifications?show=${s}${o ? `&outbox=${o}` : ""}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Notifications</h1>
          <p className="text-sm text-muted">New link alerts, decisions, task-force invites and useful tips for you. New ones arrive live.</p>
        </div>
        {(unread ?? 0) > 0 && (
          <form action={markAllRead}>
            <button className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-bg">Mark all read ({unread})</button>
          </form>
        )}
      </div>

      <nav className="flex gap-1 border-b border-line" aria-label="Which notifications">
        {(["all", "unread"] as const).map((s) => (
          <Link key={s} href={qs(s)} aria-current={s === show ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${s === show ? "border-signal font-semibold" : "border-transparent text-muted hover:text-ink"}`}>
            {s === "all" ? "All" : `Unread (${unread ?? unreadCount(list)})`}
          </Link>
        ))}
      </nav>

      {nErr && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load notifications: {nErr.message}</p>}
      {!nErr && list.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
          {show === "unread" ? "Nothing unread." : "No notifications yet."} They appear here live when the pipeline raises an alert for your station, a decision is made, or you are invited to a task force.
        </p>
      )}
      <ul className="space-y-2">
        {list.map((n) => (
          <li key={n.notification_id} className={`min-w-0 rounded-xl border bg-surface ${n.read_at ? "border-line" : "border-signal"}`}>
            <form action={openNotification}>
              <input type="hidden" name="id" value={n.notification_id} />
              <button className="block w-full p-4 text-left hover:bg-bg/50">
                <span className="flex flex-wrap items-center gap-2 text-xs">
                  {!n.read_at && <span className="h-2 w-2 rounded-full bg-signal" aria-label="unread" />}
                  <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono uppercase tracking-wider text-accent">{kindLabel(n.kind)}</span>
                  <span className="text-muted">{fmt(n.created_at)}</span>
                </span>
                <span className={`mt-1 block break-words ${n.read_at ? "" : "font-semibold"}`}>{n.title}</span>
                {n.body && <span className="mt-0.5 block break-words text-sm text-muted">{n.body}</span>}
              </button>
            </form>
          </li>
        ))}
      </ul>

      <section className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">Outbox: email and WhatsApp</h2>
          <span className="rounded-full border border-accent px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-accent">Mock · nothing is sent</span>
        </div>
        <p className="mt-1 text-sm text-muted">
          Each notification also queues the messages a deployed system would send: an email always, and a WhatsApp for alerts,
          joint-case proposals and task-force invites. This prototype only records them (spec NOT-02). Addresses are masked.
        </p>
        {officer.role === "admin" && (
          <p className="mt-2 text-sm">
            <Link className="underline" href={qs(show, allOutbox ? "" : "all")}>{allOutbox ? "Show only mine" : "Show every officer's outbox"}</Link>
          </p>
        )}
        {oErr && <p role="alert" className="mt-2 text-sm text-red-600">Could not load the outbox: {oErr.message}</p>}
        {!oErr && outbox.length === 0 && <p className="mt-3 text-sm text-muted">Nothing queued yet.</p>}
        {outbox.length > 0 && (
          <div className="-mx-5 mt-3 overflow-x-auto px-5">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr><th className="py-1 pr-3">Channel</th><th className="py-1 pr-3">To</th><th className="py-1 pr-3">Message</th><th className="py-1 pr-3">Status</th><th className="py-1">Queued</th></tr>
              </thead>
              <tbody>
                {outbox.map((o) => (
                  <tr key={o.outbox_id} className="border-t border-line align-top">
                    <td className="py-2 pr-3">{CHANNEL_LABEL[o.channel] ?? o.channel}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{o.recipient}</td>
                    <td className="py-2 pr-3">{o.payload?.title ?? "—"}</td>
                    <td className="py-2 pr-3 text-xs">{o.status === "queued" ? "queued · not sent" : o.status}{o.payload?.backfilled ? " · backfilled" : ""}{o.status === "failed" && o.payload?.error ? <span className="block text-red-600">{o.payload.error}</span> : null}</td>
                    <td className="py-2 text-xs text-muted">{fmt(o.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
