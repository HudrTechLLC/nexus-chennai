/**
 * Unit tests for the console sign-in step (one click must sign in and load /console).
 */
import { describe, expect, it, vi } from "vitest";
import { signInAndGo, signInErrorMessage } from "../signIn";

describe("signInAndGo", () => {
  it("signs in once and loads /console with one document navigation", async () => {
    const signIn = vi.fn().mockResolvedValue({ error: null });
    const go = vi.fn();
    const r = await signInAndGo("a@x.test", "pw", { signIn, go });
    expect(r).toEqual({ ok: true });
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(signIn).toHaveBeenCalledWith("a@x.test", "pw");
    expect(go).toHaveBeenCalledTimes(1);
    expect(go).toHaveBeenCalledWith("/console");
  });

  it("navigates only after sign-in has resolved (the session cookie is set first)", async () => {
    const order: string[] = [];
    const signIn = vi.fn(async () => {
      await Promise.resolve();
      order.push("signed-in");
      return { error: null };
    });
    await signInAndGo("a@x.test", "pw", { signIn, go: () => order.push("go") });
    expect(order).toEqual(["signed-in", "go"]);
  });

  it("does not navigate on wrong credentials and returns a plain message", async () => {
    const go = vi.fn();
    const r = await signInAndGo("a@x.test", "bad", { signIn: async () => ({ error: { message: "Invalid login credentials" } }), go });
    expect(r).toEqual({ ok: false, message: "Email or password is wrong." });
    expect(go).not.toHaveBeenCalled();
  });

  it("turns a thrown network failure into a message instead of leaving the form stuck", async () => {
    const go = vi.fn();
    const r = await signInAndGo("a@x.test", "pw", { signIn: async () => { throw new TypeError("Failed to fetch"); }, go });
    expect(r).toEqual({ ok: false, message: "Could not reach the sign-in service. Check the connection and try again." });
    expect(go).not.toHaveBeenCalled();
  });
});

describe("signInErrorMessage", () => {
  it("passes other server messages through and has a fallback", () => {
    expect(signInErrorMessage("Email not confirmed")).toBe("Email not confirmed");
    expect(signInErrorMessage(undefined)).toBe("Sign-in failed. Try again.");
  });
});
