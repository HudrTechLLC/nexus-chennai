/**
 * The deck tells judges to open "/login" (chief, 2026-10-27): it must land on the console sign-in page.
 * (Signed-out "/console" already goes to /console/login in middleware.ts.)
 */

import { describe, expect, it } from "vitest";
import nextConfig, { REDIRECTS } from "../../next.config.mjs";

describe("/login redirect", () => {
  it("sends /login to /console/login with a temporary redirect", async () => {
    const list = await nextConfig.redirects();
    expect(list).toBe(REDIRECTS);
    expect(list).toContainEqual({ source: "/login", destination: "/console/login", permanent: false });
  });
});
