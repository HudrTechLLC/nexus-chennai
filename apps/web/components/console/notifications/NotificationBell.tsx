"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { badgeText } from "@/lib/notifications";
import { consoleBrowserClient } from "@/lib/supabase/browser";

/**
 * Header bell with the unread count, kept live over Realtime (NOT-01, WS3-07/12).
 * Mounted once in ConsoleFrame. Postgres changes respect RLS, so only the officer's own rows arrive.
 * On the notifications page itself a change also refreshes the list.
 */
export function NotificationBell({ userId, initial }: { userId: string; initial: number }) {
  const [count, setCount] = useState(initial);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => setCount(initial), [initial]);

  useEffect(() => {
    const sb = consoleBrowserClient();
    const recount = async () => {
      const { count: n } = await sb.from("notifications").select("notification_id", { count: "exact", head: true })
        .eq("user_id", userId).is("read_at", null);
      if (typeof n === "number") setCount(n);
      if (pathname === "/console/notifications") router.refresh();
    };
    const ch = sb
      .channel(`notif-bell-${userId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "notifications", filter: `user_id=eq.${userId}` }, () => void recount())
      .subscribe();
    return () => { sb.removeChannel(ch); };
  }, [userId, pathname, router]);

  const badge = badgeText(count);
  return (
    <Link href="/console/notifications" aria-label={badge ? `Notifications, ${count} unread` : "Notifications"}
      className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-brand-line text-brand-muted hover:bg-brand-hover hover:text-brand-ink">
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      {badge && (
        <span className="absolute -right-1.5 -top-1.5 min-w-[1.25rem] rounded-full bg-accent-bright px-1 text-center font-mono text-[11px] font-bold leading-5 text-brand">
          {badge}
        </span>
      )}
    </Link>
  );
}

export default NotificationBell;
