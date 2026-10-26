/**
 * Unit tests for the login page's demo-accounts panel.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fillFrom, parseDemoLogins } from "@/lib/demoLogins";
import { DemoPanel } from "../DemoPanel";

// fake values only; the real ones live in the DEMO_LOGINS env var on the deployment
const RAW = JSON.stringify([
  { role: "admin", label: "Admin", email: "a@x.test", password: "pw-a" },
  { role: "analyst", label: "Analyst", email: "n@x.test", password: "pw-n" },
  { role: "station_officer", label: "Station officer · Adyar", email: "o1@x.test", password: "pw-o1" },
  { role: "supervisor", label: "Supervisor", email: "s@x.test", password: "pw-s" },
  { role: "station_officer", label: "Station officer · Velachery", email: "o2@x.test", password: "pw-o2" },
]);

describe("parseDemoLogins", () => {
  it("is empty when the env var is unset or junk", () => {
    expect(parseDemoLogins(undefined)).toEqual([]);
    expect(parseDemoLogins("")).toEqual([]);
    expect(parseDemoLogins("not json")).toEqual([]);
    expect(parseDemoLogins('{"email":"a@x.test"}')).toEqual([]);
    expect(parseDemoLogins('[{"email":"no-at","password":"p"},{"email":"a@x.test"},null]')).toEqual([]);
  });
  it("orders officers (env order), analyst, supervisor, admin", () => {
    expect(parseDemoLogins(RAW).map((d) => d.email)).toEqual(["o1@x.test", "o2@x.test", "n@x.test", "s@x.test", "a@x.test"]);
  });
});

describe("fillFrom", () => {
  it("fills both email and password", () => {
    expect(fillFrom(parseDemoLogins(RAW)[0])).toEqual({ email: "o1@x.test", password: "pw-o1" });
  });
});

describe("DemoPanel", () => {
  it("renders nothing when there are no demo accounts", () => {
    expect(renderToStaticMarkup(createElement(DemoPanel, { demos: [] }))).toBe("");
  });
  it("lists label + email as non-submitting buttons and never prints a password", () => {
    const html = renderToStaticMarkup(createElement(DemoPanel, { demos: parseDemoLogins(RAW) }));
    expect(html).toContain("Demo accounts");
    expect(html).toContain("Station officer · Adyar");
    expect(html).toContain("o1@x.test");
    expect((html.match(/type="button"/g) ?? []).length).toBe(5);
    expect(html).not.toContain("pw-");
  });
});
