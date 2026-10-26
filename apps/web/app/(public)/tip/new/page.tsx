import { TipForm } from "@/components/public/TipForm";
import { getAppeal } from "@/lib/publicData";
import { appealSubject } from "@/lib/tipPrefill";

export const dynamic = "force-dynamic";
export const metadata = { title: "Share information anonymously · Nexus Chennai" };

/**
 * ?appeal=<public_incident_id> prefills the form from the published appeal (WS4-12); an unknown or
 * unpublished id simply gives an empty form. ?kind=cctv picks "I have CCTV" over the derived category.
 */
export default async function NewTip({ searchParams }: { searchParams: { appeal?: string; kind?: string } }) {
  const appeal = searchParams.appeal ? await getAppeal(searchParams.appeal) : null;
  const subject = appeal ? appealSubject(appeal) : null;
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">Share information anonymously</h1>
      <p className="mt-1 text-muted">No account, no name, no phone number.</p>
      <div className="mt-6">
        <TipForm subject={subject} defaultCategory={searchParams.kind === "cctv" ? "have_cctv" : undefined} />
      </div>
    </div>
  );
}
