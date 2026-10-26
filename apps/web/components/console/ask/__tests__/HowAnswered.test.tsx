/**
 * Unit tests for Ask Nexus "How this was answered" (WS3-30).
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@/components/console/alerts/AlertMapLoader", () => ({ AlertMapLoader: () => null }));
vi.mock("@/lib/supabase/browser", () => ({ consoleBrowserClient: () => ({}) }));

import { HowAnswered } from "../AskNexus";
import type { AskQuestion } from "@/lib/ask";

const q: AskQuestion = {
  question_id: "q1", asked_by: "u1", question: "House breaks in Adyar", status: "answered",
  created_at: "2026-10-27T03:00:00Z", started_at: null, answered_at: null,
  run_id: "ask_123", model: "claude-sonnet", routed_model: "claude-haiku", receipt_id: "rcpt-9", error: null,
  plan: {
    understood: "House breaks at Adyar station this month",
    filters: [{ field: "station_id", op: "eq", value: "PS-ADYAR-J2", label: "Station: Adyar" }],
    steps: [{ query: "crimes_by_filter", purpose: "Find matching house breaks", query_id: "zq-77", rows: 4 }],
    model_plan: { steps: 1 },
  },
  answer: { summary: "4 house breaks.", total: 4, truncated: false, rows: [] },
};

describe("HowAnswered", () => {
  it("shows filter labels, query names, row counts, model, routing and receipt", () => {
    const html = renderToStaticMarkup(<HowAnswered q={q} canOpenTrace={false} />);
    expect(html).toContain("Station: Adyar");
    expect(html).not.toContain("PS-ADYAR-J2");
    expect(html).toContain("crimes_by_filter");
    expect(html).toContain("4 rows");
    expect(html).toContain("zq-77");
    expect(html).toContain("routed to claude-haiku");
    expect(html).toContain("rcpt-9");
    expect(html).toContain("raw plan");
  });
  it("links the full trace for admins only", () => {
    expect(renderToStaticMarkup(<HowAnswered q={q} canOpenTrace={false} />)).not.toContain("/console/system/trace/");
    expect(renderToStaticMarkup(<HowAnswered q={q} canOpenTrace />)).toContain("/console/system/trace/ask_123");
  });
});
