"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getOfficer } from "@/lib/auth";
import { safeLink } from "@/lib/notifications";
import { consoleServerClient } from "@/lib/supabase/server";

/**
 * Open a notification: mark it read (RLS: own rows, read_at only) and go to its target.
 * Plain form action, so it works without client JS.
 */
export async function openNotification(formData: FormData): Promise<void> {
  const officer = await getOfficer();
  if (!officer) redirect("/console/login");
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) redirect("/console/notifications");
  const sb = consoleServerClient();
  const { data } = await sb.from("notifications").select("link, read_at").eq("notification_id", id).maybeSingle();
  if (data && !data.read_at) {
    await sb.from("notifications").update({ read_at: new Date().toISOString() }).eq("notification_id", id);
  }
  revalidatePath("/console", "layout");
  redirect(safeLink(data?.link) ?? "/console/notifications");
}

/** Mark every unread notification of the signed-in officer as read. */
export async function markAllRead(): Promise<void> {
  const officer = await getOfficer();
  if (!officer) redirect("/console/login");
  await consoleServerClient()
    .from("notifications")
    .update({ read_at: new Date().toISOString() })
    .eq("user_id", officer.userId)
    .is("read_at", null);
  revalidatePath("/console", "layout");
}
