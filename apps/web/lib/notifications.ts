/**
 * In-app notifications and the mock outbox (spec B7 NOT-01, NOT-02; G2 /console/notifications; WS3-12).
 * Types plus pure helpers shared by the page, the bell and the tests. Rows come from 0002 + 0004_10.
 */

// =====================
// Types
// =====================

export type AppNotification = {
  notification_id: number;
  user_id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
};

export type OutboxRow = {
  outbox_id: number;
  channel: "email" | "whatsapp" | "in_app";
  recipient: string;
  payload: { notification_id?: number; kind?: string; title?: string; body?: string | null; link?: string | null; backfilled?: boolean; error?: string };
  status: "queued" | "sent" | "failed";
  created_at: string;
  user_id: string | null;
};

// =====================
// Labels
// =====================

export const KIND_LABEL: Record<string, string> = {
  link_alert: "New link alert",
  alert_decision: "Alert decision",
  joint_case_proposal: "Joint case proposed",
  taskforce_invite: "Task force invite",
  tip_useful: "Useful tip",
};

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind.replace(/_/g, " ");
}

export const CHANNEL_LABEL: Record<OutboxRow["channel"], string> = { email: "Email", whatsapp: "WhatsApp", in_app: "In-app" };

// =====================
// Filters and links
// =====================

export const SHOWS = ["all", "unread"] as const;
export type Show = (typeof SHOWS)[number];

export function parseShow(v: string | undefined): Show {
  return v === "unread" ? "unread" : "all";
}

/**
 * Where opening a notification goes. Only same-site console paths are followed, so a stored link
 * can never send an officer off the console; anything else falls back to the list.
 */
export function safeLink(link: string | null | undefined): string | null {
  if (!link || !link.startsWith("/console/") || link.startsWith("//") || /[\\\s]/.test(link)) return null;
  return link;
}

export function unreadCount(rows: Pick<AppNotification, "read_at">[]): number {
  return rows.reduce((n, r) => n + (r.read_at ? 0 : 1), 0);
}

/** Bell badge text: nothing at 0, the number up to 99, then "99+". */
export function badgeText(n: number): string | null {
  if (n <= 0) return null;
  return n > 99 ? "99+" : String(n);
}
