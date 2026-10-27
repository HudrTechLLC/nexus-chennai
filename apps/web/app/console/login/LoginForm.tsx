"use client";
import { useEffect, useRef, useState } from "react";
import { consoleBrowserClient } from "@/lib/supabase/browser";
import { DemoPanel } from "@/components/console/login/DemoPanel";
import { SignInButton, SignInStatus } from "@/components/console/login/SignInButton";
import { fillFrom, type DemoLogin } from "@/lib/demoLogins";
import { signInAndGo } from "@/lib/signIn";

export function LoginForm({ demos = [] }: { demos?: DemoLogin[] }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);

  // Back from /console restores this page from the back-forward cache with the old pending state.
  useEffect(() => {
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        inFlight.current = false;
        setBusy(false);
      }
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  /** Demo account picked: fill the form (admin: email only, focus the password); the user still presses Sign in. */
  function pick(d: DemoLogin) {
    if (inFlight.current) return;
    const f = fillFrom(d);
    setEmail(f.email);
    setPassword(f.password);
    setError(null);
    setPicked(d.email);
    if (f.focusPassword) passwordRef.current?.focus();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current) return; // one sign-in at a time
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const result = await signInAndGo(email, password, {
      signIn: (em, pw) => consoleBrowserClient().auth.signInWithPassword({ email: em, password: pw }),
      go: (path) => window.location.assign(path),
    });
    if (!result.ok) {
      inFlight.current = false;
      setBusy(false);
      setError(result.message);
    }
    // on success stay pending: the console page is loading and will replace this one
  }

  return (
    <>
    <form onSubmit={submit} aria-busy={busy} className="mx-auto mt-6 max-w-sm space-y-3 rounded-xl border border-line bg-surface p-5">
      <label className="block text-sm">
        <span className="text-muted">Email</span>
        <input
          type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} readOnly={busy}
          className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted">Password</span>
        <input
          ref={passwordRef} type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} readOnly={busy}
          className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
        />
      </label>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <SignInButton pending={busy} />
      <SignInStatus pending={busy} />
    </form>
    <DemoPanel demos={demos} picked={picked} onPick={pick} />
    </>
  );
}
