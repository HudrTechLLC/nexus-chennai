"use client";
import dynamic from "next/dynamic";
import type { AlertMapProps } from "./AlertMap";

/** deck.gl and MapLibre need WebGL, so the alert map renders only in the browser (fixed height, see AlertMap). */
const AlertMap = dynamic(() => import("./AlertMap"), {
  ssr: false,
  loading: () => <div className="grid h-72 place-items-center rounded-xl border border-line bg-surface text-sm text-muted">Loading the map…</div>,
});

export function AlertMapLoader(props: AlertMapProps) {
  return <AlertMap {...props} />;
}
