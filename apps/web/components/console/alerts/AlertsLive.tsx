"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { consoleBrowserClient } from "@/lib/supabase/browser";

/**
 * Realtime: new or changed link alerts and new decisions refresh the page (spec WS3-07).
 * Postgres changes respect RLS, so an officer only hears about rows they may read.
 */
export function AlertsLive({ alertId }: { alertId?: string }) {
  const router = useRouter();
  const [toast, setToast] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    const sb = consoleBrowserClient();
    const show = (msg: string) => {
      setToast(msg);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setToast(null), 6000);
      router.refresh();
    };
    const alertFilter = alertId ? { filter: `alert_id=eq.${alertId}` } : {};
    const ch = sb
      .channel(alertId ? `alert-${alertId}` : "alerts-inbox")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "link_alerts", ...alertFilter }, (p) =>
        show(`New link alert ${(p.new as { alert_id?: string }).alert_id ?? ""}`))
      .on("postgres_changes", { event: "UPDATE", schema: "public", table: "link_alerts", ...alertFilter }, (p) =>
        show(`Alert ${(p.new as { alert_id?: string }).alert_id ?? ""} is now ${(p.new as { status?: string }).status ?? "updated"}`))
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "alert_decisions", ...alertFilter }, () =>
        show("A decision was recorded"))
      .subscribe();
    return () => {
      clearTimeout(timer.current);
      sb.removeChannel(ch);
    };
  }, [alertId, router]);

  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50">
      {toast && <div className="rounded-lg bg-ink px-4 py-2 text-sm text-bg shadow-lg">{toast}</div>}
    </div>
  );
}
