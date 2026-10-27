/**
 * Unit tests for the sign-in button's pending state.
 */
import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SignInButton, SignInStatus } from "../SignInButton";

describe("SignInButton", () => {
  it("is an enabled submit button reading 'Sign in' when idle, with no spinner", () => {
    const html = renderToStaticMarkup(createElement(SignInButton, { pending: false }));
    expect(html).toContain('type="submit"');
    expect(html).not.toContain('disabled=""');
    expect(html).toContain('aria-disabled="false"');
    expect(html).toContain(">Sign in<");
    expect(html).not.toContain("animate-spin");
  });

  it("is disabled with a spinner and 'Signing in…' while pending", () => {
    const html = renderToStaticMarkup(createElement(SignInButton, { pending: true }));
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-disabled="true"');
    expect(html).toContain("animate-spin");
    expect(html).toContain("Signing in…");
  });
});

describe("SignInStatus", () => {
  it("announces 'Signing in…' politely only while pending", () => {
    expect(renderToStaticMarkup(createElement(SignInStatus, { pending: true }))).toContain('aria-live="polite"');
    expect(renderToStaticMarkup(createElement(SignInStatus, { pending: true }))).toContain("Signing in…");
    expect(renderToStaticMarkup(createElement(SignInStatus, { pending: false }))).not.toContain("Signing in");
  });
});
