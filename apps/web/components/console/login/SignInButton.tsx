import { Loader2 } from "lucide-react";

/**
 * The sign-in submit button. While pending it is disabled and shows a spinner with "Signing in…";
 * it stays that way until the console page replaces this one.
 */
export function SignInButton({ pending }: { pending: boolean }) {
  return (
    <button
      type="submit"
      disabled={pending}
      aria-disabled={pending}
      className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-signal px-3 py-2 font-medium text-white disabled:cursor-wait disabled:opacity-80"
    >
      {pending && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />}
      {pending ? "Signing in…" : "Sign in"}
    </button>
  );
}

/** Polite live status for screen readers: announces the pending sign-in. Errors use role="alert". */
export function SignInStatus({ pending }: { pending: boolean }) {
  return (
    <p aria-live="polite" className="sr-only">
      {pending ? "Signing in…" : ""}
    </p>
  );
}
