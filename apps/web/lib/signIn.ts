/**
 * The console sign-in step, kept free of React and Supabase so it can be unit-tested.
 *
 * Why a full page load after sign-in: the form used to call router.replace("/console") and then
 * router.refresh() straight after. In Next 14 the refresh re-renders the CURRENT route (still
 * /console/login) and can cancel the pending navigation, so the first click often left the user on
 * the login page with the button re-enabled and no feedback; a second click "worked". A document
 * navigation sends the new session cookie to the middleware and has no client router cache or race.
 */

export type SignInResult = { ok: true } | { ok: false; message: string };

export interface SignInDeps {
  /** Supabase signInWithPassword, or a stub in tests. */
  signIn: (email: string, password: string) => Promise<{ error: { message: string } | null }>;
  /** Navigate the whole document (window.location.assign in the app). */
  go: (path: string) => void;
}

/** Plain-language message for a failed sign-in. */
export function signInErrorMessage(message: string | undefined): string {
  if (!message) return "Sign-in failed. Try again.";
  if (message === "Invalid login credentials") return "Email or password is wrong.";
  if (/fetch|network/i.test(message)) return "Could not reach the sign-in service. Check the connection and try again.";
  return message;
}

/**
 * Sign in, then load /console. On success the caller keeps its pending state: the page is about to
 * be replaced. On failure it gets a message to show and should restore the form.
 */
export async function signInAndGo(email: string, password: string, deps: SignInDeps, to = "/console"): Promise<SignInResult> {
  let error: { message: string } | null;
  try {
    ({ error } = await deps.signIn(email, password));
  } catch (e) {
    return { ok: false, message: signInErrorMessage(e instanceof Error ? e.message : undefined) };
  }
  if (error) return { ok: false, message: signInErrorMessage(error.message) };
  deps.go(to);
  return { ok: true };
}
