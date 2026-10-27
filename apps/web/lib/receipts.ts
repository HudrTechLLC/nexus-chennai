/**
 * Labels for the id a model call left in the trace (`receipt_id`). The API stores Nightshift's own receipt when the
 * reply carries one (an `rcpt_…` id from the receipt header), otherwise the OpenAI-style completion id
 * (`chatcmpl-…`, nightshift.py `_receipt_id`). Only the first is a Nightshift receipt, so the UI never calls the
 * second one a receipt.
 */

import matches from "@/content/receipt_matches.json";

export type ReceiptKind = "nightshift" | "completion" | "other";

/**
 * Completion ids matched offline to a signed Nightshift receipt (scripts/receipt_matches.py: every receipt for the
 * id in Nightshift's log carries a valid Ed25519 signature from the pinned key). Ids only; regenerate after new runs.
 */
const MATCHED: ReadonlySet<string> = new Set((matches as { ids: string[] }).ids);

/** True when this completion id was matched to a signed Nightshift receipt. */
export function isMatched(id: string | null | undefined, matched: ReadonlySet<string> = MATCHED): boolean {
  return !!id && matched.has(id);
}

/** Which kind of id this is. */
export function receiptKind(id: string | null | undefined): ReceiptKind | null {
  if (!id) return null;
  if (/^rcpt_/i.test(id)) return "nightshift";
  if (/^chatcmpl-/i.test(id)) return "completion";
  return "other";
}

/** The label shown before a single id. */
export function receiptLabel(id: string | null | undefined, matched: ReadonlySet<string> = MATCHED): string | null {
  switch (receiptKind(id)) {
    case "nightshift": return "Nightshift receipt";
    case "completion": return isMatched(id, matched) ? "completion id" : "completion id (not yet matched to a Nightshift receipt)";
    case "other": return "model call id";
    default: return null;
  }
}

/** A short note after a completion id that was matched, e.g. "· signed Nightshift receipt ✓". */
export function receiptNote(id: string | null | undefined, matched: ReadonlySet<string> = MATCHED): string | null {
  return receiptKind(id) === "completion" && isMatched(id, matched) ? "signed Nightshift receipt ✓" : null;
}

/** Counts by kind, for a summary such as a run header or a dossier footer. */
export function receiptCounts(ids: (string | null | undefined)[]): { nightshift: number; completion: number; other: number } {
  const n = { nightshift: 0, completion: 0, other: 0 };
  for (const id of ids) { const k = receiptKind(id); if (k) n[k] += 1; }
  return n;
}

/**
 * Summary for a set of ids, e.g. "27 completion ids · all 27 matched to signed Nightshift receipts (verified offline)".
 * Unmatched completion ids are counted, never hidden.
 */
export function receiptCountLine(ids: (string | null | undefined)[], matched: ReadonlySet<string> = MATCHED): string {
  const n = receiptCounts(ids);
  const plural = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  const parts: string[] = [];
  if (n.nightshift) parts.push(plural(n.nightshift, "Nightshift receipt", "Nightshift receipts"));
  if (n.completion) {
    const ok = ids.filter((id) => receiptKind(id) === "completion" && isMatched(id, matched)).length;
    let line = plural(n.completion, "completion id", "completion ids");
    if (ok === n.completion) line += ` · ${n.completion === 1 ? "matched to a signed Nightshift receipt" : `all ${ok} matched to signed Nightshift receipts`} (verified offline)`;
    else if (ok > 0) line += ` · ${ok} matched to signed Nightshift receipts (verified offline), ${n.completion - ok} not yet matched`;
    else line += " · not yet matched to Nightshift receipts";
    parts.push(line);
  }
  if (n.other) parts.push(plural(n.other, "model call id", "model call ids"));
  return parts.length ? parts.join(" · ") : "no model call ids";
}
