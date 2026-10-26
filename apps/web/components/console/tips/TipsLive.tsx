"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { consoleBrowserClient } from "@/lib/supabase/browser";

/** Refresh the triage queue when tips arrive or the worker screens them (Realtime, RLS applies). */
export function TipsLive() {
  const router = useRouter();
  useEffect(() => {
    const sb = consoleBrowserClient();
    const ch = sb.channel("tips-queue")
      .on("postgres_changes", { event: "*", schema: "public", table: "tips" }, () => router.refresh())
      .subscribe();
    return () => { sb.removeChannel(ch); };
  }, [router]);
  return null;
}
