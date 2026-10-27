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
  { role: "admin", label: "Admin", email: "a@x.test" },
  { role: "analyst", label: "Analyst", email: "n@x.test", password: "pw-n" },
  { role: "station_officer", label: "Station officer · Adyar", email: "o1@x.test", password: "pw-o1" },
  { role: "supervisor", label: "Supervisor", email: "s@x.test", password: "pw-s" },
  { role: "station_officer", label: "Station officer", station: "Velachery", email: "o2@x.test", password: "pw-o2" },
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

  it("keeps an admin entry without a password", () => {
    const admin = parseDemoLogins(RAW).find((d) => d.role === "admin");
    expect(admin).toMatchObject({ email: "a@x.test", password: null });
  });

  it("drops an admin password from the env, so it never reaches the browser", () => {
    const [admin] = parseDemoLogins(JSON.stringify([{ role: "admin", email: "a@x.test", password: "pw-admin" }]));
    expect(admin.password).toBeNull();
    expect(JSON.stringify(admin)).not.toContain("pw-admin");
  });

  it("still drops a non-admin entry without a password", () => {
    expect(parseDemoLogins(JSON.stringify([{ role: "analyst", email: "n@x.test" }]))).toEqual([]);
    expect(parseDemoLogins(JSON.stringify([{ role: "analyst", email: "n@x.test", password: "" }]))).toEqual([]);
  });

  it("takes the officer station from `station`, else from the label after ' · '; only officers get one", () => {
    const by = Object.fromEntries(parseDemoLogins(RAW).map((d) => [d.email, d.station]));
    expect(by["o1@x.test"]).toBe("Adyar");
    expect(by["o2@x.test"]).toBe("Velachery");
    expect(by["n@x.test"]).toBeNull();
    expect(by["a@x.test"]).toBeNull();
  });
});

describe("fillFrom", () => {
  it("fills both email and password for an officer, without moving focus", () => {
    expect(fillFrom(parseDemoLogins(RAW)[0])).toEqual({ email: "o1@x.test", password: "pw-o1", focusPassword: false });
  });

  it("fills the admin email only, clears the password and asks for focus there", () => {
    const admin = parseDemoLogins(RAW).find((d) => d.role === "admin")!;
    expect(fillFrom(admin)).toEqual({ email: "a@x.test", password: "", focusPassword: true });
  });
});

describe("DemoPanel", () => {
  it("renders nothing when there are no demo accounts", () => {
    expect(renderToStaticMarkup(createElement(DemoPanel, { demos: [] }))).toBe("");
  });

  it("shows all five as non-submitting tiles in one responsive row, and never prints a password", () => {
    const html = renderToStaticMarkup(createElement(DemoPanel, { demos: parseDemoLogins(RAW) }));
    expect(html).toContain("Demo accounts");
    expect(html).toContain("lg:grid-cols-5");
    expect((html.match(/type="button"/g) ?? []).length).toBe(5);
    expect(html).toContain("Station officer");
    expect(html).toContain("Adyar");
    expect(html).toContain("Velachery");
    expect(html.replace(/<wbr\/>/g, "")).toContain("o1@x.test"); // <wbr> lets the email wrap at the @
    expect(html).not.toContain("pw-");
  });

  it("marks only the admin tile as 'Type the password'", () => {
    const html = renderToStaticMarkup(createElement(DemoPanel, { demos: parseDemoLogins(RAW) }));
    expect((html.match(/Type the password/g) ?? []).length).toBe(1);
  });

  it("announces the admin pick as type-the-password", () => {
    const html = renderToStaticMarkup(createElement(DemoPanel, { demos: parseDemoLogins(RAW), picked: "a@x.test" }));
    expect(html).toContain("Filled a@x.test. Type the password, then press Sign in.");
  });
});
