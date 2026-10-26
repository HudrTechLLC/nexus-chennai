/**
 * Unit tests for notification helpers (WS3-12).
 */
import { describe, expect, it } from "vitest";
import { badgeText, kindLabel, parseShow, safeLink, unreadCount } from "../notifications";

describe("kindLabel", () => {
  it("labels known kinds and humanises unknown ones", () => {
    expect(kindLabel("taskforce_invite")).toBe("Task force invite");
    expect(kindLabel("tip_useful")).toBe("Useful tip");
    expect(kindLabel("daily_briefing")).toBe("daily briefing");
  });
});

describe("parseShow", () => {
  it("defaults to all", () => {
    expect(parseShow(undefined)).toBe("all");
    expect(parseShow("junk")).toBe("all");
    expect(parseShow("unread")).toBe("unread");
  });
});

describe("safeLink", () => {
  it("follows console paths only", () => {
    expect(safeLink("/console/alerts/LA-2026-E38C6B38B865")).toBe("/console/alerts/LA-2026-E38C6B38B865");
    expect(safeLink("/console/taskforces/new?alert_id=LA-1")).toBe("/console/taskforces/new?alert_id=LA-1");
  });
  it("refuses anything that could leave the console", () => {
    expect(safeLink(null)).toBeNull();
    expect(safeLink("https://evil.example/console/x")).toBeNull();
    expect(safeLink("//evil.example/console/x")).toBeNull();
    expect(safeLink("/console\\..\\x")).toBeNull();
    expect(safeLink("/tips/x")).toBeNull();
  });
});

describe("unreadCount and badgeText", () => {
  it("counts unread rows", () => {
    expect(unreadCount([{ read_at: null }, { read_at: "2026-10-26T10:00:00Z" }, { read_at: null }])).toBe(2);
  });
  it("hides the badge at zero and caps at 99+", () => {
    expect(badgeText(0)).toBeNull();
    expect(badgeText(7)).toBe("7");
    expect(badgeText(150)).toBe("99+");
  });
});
