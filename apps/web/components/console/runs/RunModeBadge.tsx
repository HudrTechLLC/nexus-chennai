import { Database, FlaskConical, HelpCircle } from "lucide-react";
import { Badge } from "@/components/ui";

/**
 * LIVE / SAMPLE badge for a run, from the run's own recorded flag (lib/trace.ts runMode): never assumed.
 * "unknown" means the run's steps were readable but did not record the flag; render nothing when the steps
 * could not be read at all (e.g. an officer, whom trace RLS does not let see them).
 */
export function RunModeBadge({ mode }: { mode: "live" | "sample" | "unknown" }) {
  if (mode === "live")
    return <Badge tone="signal" icon={Database} title="This run had sample mode off: every Zetaris query and model call was live.">Live data</Badge>;
  if (mode === "sample")
    return <Badge tone="warn" icon={FlaskConical} title="This run had sample mode on: it was allowed to fall back to the bundled sample data. The trace shows which steps did.">Sample mode</Badge>;
  return <Badge tone="neutral" icon={HelpCircle} title="This run did not record whether sample mode was on.">Mode not recorded</Badge>;
}

export default RunModeBadge;
