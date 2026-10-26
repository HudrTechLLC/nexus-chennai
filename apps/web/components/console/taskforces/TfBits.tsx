import { STATUS_LABEL, type TfStatus } from "@/lib/taskforces";

export function TfStatusPill({ status }: { status: TfStatus }) {
  const cls = {
    proposed: "border-accent text-accent",
    active: "border-signal text-signal",
    closed: "border-line text-muted",
    declined: "border-red-500 text-red-600",
  }[status] ?? "border-line text-muted";
  return <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${cls}`}>{STATUS_LABEL[status] ?? status}</span>;
}
