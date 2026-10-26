"use client";
import dynamic from "next/dynamic";
import type { Role } from "@/lib/roles";

/** deck.gl and MapLibre need the browser (WebGL), so the Pulse Map never renders on the server. */
const PulseMap = dynamic(() => import("./PulseMap"), {
  ssr: false,
  loading: () => <div className="grid h-[calc(100vh-9rem)] place-items-center rounded-xl border border-line bg-surface text-sm text-muted">Loading the Pulse Map…</div>,
});

export function PulseMapLoader(props: { stationId: string | null; role: Role }) {
  return <PulseMap {...props} />;
}
