/**
 * Labels for the id a model call left in the trace (`receipt_id`). The API stores Nightshift's own receipt when the
 * reply carries one (an `rcpt_…` id from the receipt header), otherwise the OpenAI-style completion id
 * (`chatcmpl-…`, nightshift.py `_receipt_id`). Only the first is a Nightshift receipt, so the UI never calls the
 * second one a receipt.
 */

export type ReceiptKind = "nightshift" | "completion" | "other";

/** Which kind of id this is. */
export function receiptKind(id: string | null | undefined): ReceiptKind | null {
  if (!id) return null;
  if (/^rcpt_/i.test(id)) return "nightshift";
  if (/^chatcmpl-/i.test(id)) return "completion";
  return "other";
}

/** The label shown before a single id. */
export function receiptLabel(id: string | null | undefined): string | null {
  switch (receiptKind(id)) {
    case "nightshift": return "Nightshift receipt";
    case "completion": return "completion id (no Nightshift receipt id)";
    case "other": return "model call id";
    default: return null;
  }
}

/** Counts by kind, for a summary such as a run header or a dossier footer. */
export function receiptCounts(ids: (string | null | undefined)[]): { nightshift: number; completion: number; other: number } {
  const n = { nightshift: 0, completion: 0, other: 0 };
  for (const id of ids) { const k = receiptKind(id); if (k) n[k] += 1; }
  return n;
}

/** "3 Nightshift receipts · 2 completion ids", or "2 completion ids (no Nightshift receipt id)" when none is a receipt. */
export function receiptCountLine(ids: (string | null | undefined)[]): string {
  const n = receiptCounts(ids);
  const plural = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  const parts: string[] = [];
  if (n.nightshift) parts.push(plural(n.nightshift, "Nightshift receipt", "Nightshift receipts"));
  if (n.completion) parts.push(plural(n.completion, "completion id", "completion ids") + (n.nightshift ? "" : " (no Nightshift receipt id)"));
  if (n.other) parts.push(plural(n.other, "model call id", "model call ids"));
  return parts.length ? parts.join(" · ") : "no model call ids";
}
