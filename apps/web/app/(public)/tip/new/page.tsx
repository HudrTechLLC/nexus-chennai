import { TipForm } from "@/components/public/TipForm";
import { Lock } from "lucide-react";
import { HexPattern } from "@/components/public/HexPattern";
import { getAppeal, getCrimeCard } from "@/lib/publicData";
import { appealSubject, crimeSubject } from "@/lib/tipPrefill";

export const dynamic = "force-dynamic";
export const metadata = { title: "Share information anonymously · Nexus Chennai" };

/**
 * ?appeal=<public_incident_id> or ?about=<public crime-card id> prefills the form from public fields
 * (WS4-12); an unknown, unpublished or no-longer-public id simply gives an empty form. If both are given
 * the appeal wins. ?kind=cctv picks "I have CCTV" over the derived category.
 */
export default async function NewTip({ searchParams }: { searchParams: { appeal?: string; about?: string; kind?: string } }) {
  const appeal = searchParams.appeal ? await getAppeal(searchParams.appeal) : null;
  const card = !appeal && searchParams.about ? await getCrimeCard(searchParams.about) : null;
  const subject = appeal ? appealSubject(appeal) : card ? crimeSubject(card) : null;
  return (
    <div className="mx-auto max-w-2xl">
      <div className="relative isolate flex items-start gap-4 overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-signal-soft via-surface to-accent-soft p-6">
        <HexPattern />
        <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-signal text-on-signal shadow-card">
          <Lock className="size-6" aria-hidden />
        </span>
        <div>
          <h1 className="text-3xl font-bold">Share information anonymously</h1>
          <p className="mt-1 text-muted">No account, no name, no phone number.</p>
        </div>
      </div>
      <div className="mt-6">
        <TipForm subject={subject} defaultCategory={searchParams.kind === "cctv" ? "have_cctv" : undefined} />
      </div>
    </div>
  );
}
