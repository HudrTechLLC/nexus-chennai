/**
 * Unit tests for rewriteHref: markdown links inside engg/docs notes must land on docs-site routes.
 */

import { describe, it, expect } from "vitest";
import { rewriteHref, type DocsIndex } from "../docs";

const index: DocsIndex = {
  tabs: [
    { id: "overview", label: "Overview", title: "Overview" },
    { id: "demo", label: "Demo", title: "Demo" },
  ],
  notes: [
    { slug: "00-index", file: "00-INDEX.md", label: "Index" },
    { slug: "hackathon-rules-check", file: "hackathon/RULES_CHECK.md", label: "Rules check" },
    { slug: "submission-evidence", file: "submission/EVIDENCE.md", label: "Submission evidence" },
    { slug: "submission-deck", file: "submission/DECK.md", label: "Deck" },
  ],
  builtAt: "2026-10-26T00:00:00Z",
};

describe("rewriteHref", () => {
  it("leaves external links alone", () => {
    expect(rewriteHref("https://example.com/x", index)).toBe("https://example.com/x");
  });

  it("maps a sibling link inside submission/ to its note", () => {
    expect(rewriteHref("EVIDENCE.md", index)).toBe("/docs/notes/submission-evidence");
    expect(rewriteHref("DECK.md", index)).toBe("/docs/notes/submission-deck");
  });

  it("maps a sibling link inside hackathon/ to its note", () => {
    expect(rewriteHref("RULES_CHECK.md", index)).toBe("/docs/notes/hackathon-rules-check");
  });

  it("maps a parent-relative link from a subfolder note", () => {
    expect(rewriteHref("../hackathon/RULES_CHECK.md", index)).toBe("/docs/notes/hackathon-rules-check");
    expect(rewriteHref("../00-INDEX.md", index)).toBe("/docs/notes/00-index");
  });

  it("maps SPEC anchors to spec tabs", () => {
    expect(rewriteHref("../SPEC.md#demo", index)).toBe("/docs/demo");
  });
});
