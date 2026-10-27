import { AppealCard } from "@/components/public/AppealCard";
import { HexPattern } from "@/components/public/HexPattern";
import { getAppeals } from "@/lib/publicData";

export const revalidate = 60;
export const metadata = { title: "Police appeals · Nexus Chennai" };

export default async function Appeals() {
  const { appeals, error } = await getAppeals();
  return (
    <div className="space-y-6">
      <div className="relative isolate overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-signal-soft via-surface to-accent-soft p-6 sm:p-8">
        <HexPattern />
        <h1 className="text-3xl font-bold">Police appeals</h1>
        <p className="mt-1 max-w-prose text-muted">
          Incidents the police have asked the public about. Details are cleaned before publishing: no exact places, no victim details.
        </p>
      </div>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {!error && appeals.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-muted">No open appeals right now.</p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {appeals.map((a) => <AppealCard key={a.id} a={a} />)}
      </div>
    </div>
  );
}
