import { TipForm } from "@/components/public/TipForm";
import { getAppeal } from "@/lib/publicData";

export const dynamic = "force-dynamic";
export const metadata = { title: "Share information anonymously · Nexus Chennai" };

export default async function NewTip({ searchParams }: { searchParams: { appeal?: string; kind?: string } }) {
  const appeal = searchParams.appeal ? await getAppeal(searchParams.appeal) : null;
  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">Share information anonymously</h1>
      <p className="mt-1 text-muted">No account, no name, no phone number.</p>
      <div className="mt-6">
        <TipForm
          appeal={appeal?.id ?? null}
          appealTitle={appeal ? `${appeal.title} · ${appeal.area} · ${appeal.week}` : null}
          defaultCategory={searchParams.kind === "cctv" ? "have_cctv" : undefined}
        />
      </div>
    </div>
  );
}
