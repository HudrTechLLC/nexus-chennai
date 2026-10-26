import { ConsoleFrame } from "@/components/console/ConsoleFrame";
import { NoRole } from "@/components/console/NoRole";
import { getOfficer } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const officer = await getOfficer();
  // The middleware already sent signed-out visitors to /console/login; this is an account with no police profile.
  if (!officer) return <NoRole />;
  return <ConsoleFrame officer={officer}>{children}</ConsoleFrame>;
}
