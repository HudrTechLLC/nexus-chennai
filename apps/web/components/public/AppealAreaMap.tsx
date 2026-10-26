"use client";
import dynamic from "next/dynamic";

/** Client-only loader for the appeal's area map (MapLibre needs the browser). */
export const AppealAreaMap = dynamic(() => import("./AreaMap"), {
  ssr: false, loading: () => <div className="h-56 w-full rounded-lg border border-line bg-bg" />,
});
