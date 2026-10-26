import { ConsoleFrame } from "@/components/console/ConsoleFrame";
import { NoRole } from "@/components/console/NoRole";
import { getOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const officer = await getOfficer();
  // The middleware already sent signed-out visitors to /console/login; this is an account with no police profile.
  if (!officer) return <NoRole />;
  const { count } = await consoleServerClient().from("notifications")
    .select("notification_id", { count: "exact", head: true }).eq("user_id", officer.userId).is("read_at", null);
  return <ConsoleFrame officer={officer} unread={count ?? 0}>{children}</ConsoleFrame>;
}
