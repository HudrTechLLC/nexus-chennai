import { redirect } from "next/navigation";

/** Old link: the tip form lives at /tip/new (spec G1). */
export default function TipIndex({ searchParams }: { searchParams: { appeal?: string } }) {
  redirect(searchParams.appeal ? `/tip/new?appeal=${encodeURIComponent(searchParams.appeal)}` : "/tip/new");
}
