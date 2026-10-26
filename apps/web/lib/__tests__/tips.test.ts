import { describe, expect, it } from "vitest";
import { guardBadges, parseTipTab, statusesFor, validatePoliceReply, validateReview } from "../tips";

describe("tabs", () => {
  it("maps tabs to statuses; quarantined tips have their own visible tab", () => {
    expect(statusesFor("triage")).toEqual(["new", "screened"]);
    expect(statusesFor("quarantined")).toEqual(["quarantined"]);
    expect(statusesFor("all")).toBeNull();
    expect(parseTipTab("nope")).toBe("triage");
  });
});

describe("guardBadges", () => {
  it("says when a tip is not screened yet", () => {
    expect(guardBadges(null, "new")[0].label).toBe("Not screened yet");
  });
  it("summarises a quarantined injection attempt", () => {
    const b = guardBadges({ action: "quarantine", injection: true, spam_score: 0.1 }, "quarantined").map((x) => x.label);
    expect(b).toContain("Guard: quarantined");
    expect(b).toContain("Prompt-injection attempt");
    expect(b).toContain("Spam 10%");
  });
  it("accepts the D3.6 verdict shape", () => {
    expect(guardBadges({ verdict: "clean", injection: false, spam_score: 0.04, threat: false }, "screened")[0]).toEqual({ label: "Guard: clean", tone: "ok" });
  });
});

describe("validation", () => {
  it("review needs a yes/no", () => {
    expect(validateReview({ useful: undefined })).toMatch(/useful/);
    expect(validateReview({ useful: false, note: "x" })).toBeNull();
  });
  it("cannot reply to a fully anonymous tip", () => {
    expect(validatePoliceReply("thanks", false)).toMatch(/anonymity/);
    expect(validatePoliceReply("Thanks, can you share the CCTV time?", true)).toBeNull();
  });
});
