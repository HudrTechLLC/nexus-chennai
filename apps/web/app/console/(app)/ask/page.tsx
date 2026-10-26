import { requireOfficer } from "@/lib/auth";
import { AskNexus } from "@/components/console/ask/AskNexus";

export const dynamic = "force-dynamic";
export const metadata = { title: "Ask Nexus · Nexus Chennai" };

/** Ask Nexus (WS3-30): a question in plain English, answered by Zetaris queries the worker plans and runs. */
export default async function AskPage() {
  const officer = await requireOfficer("analyst+");
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Ask Nexus</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Ask about crimes in plain English. Nexus turns the question into Zetaris queries, runs them, and shows every
          case it found with the reason it matched. You only see cases your role can open.
        </p>
      </div>
      <AskNexus canOpenTrace={officer.role === "admin"} />
    </div>
  );
}
