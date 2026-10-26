"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { consoleBrowserClient } from "@/lib/supabase/browser";
import { DemoPanel } from "@/components/console/login/DemoPanel";
import { fillFrom, type DemoLogin } from "@/lib/demoLogins";

export function LoginForm({ demos = [] }: { demos?: DemoLogin[] }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);

  /** Demo account picked: fill both fields; the user still presses Sign in. */
  function pick(d: DemoLogin) {
    const f = fillFrom(d);
    setEmail(f.email);
    setPassword(f.password);
    setError(null);
    setPicked(d.email);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error: err } = await consoleBrowserClient().auth.signInWithPassword({ email, password });
    setBusy(false);
    if (err) {
      setError(err.message === "Invalid login credentials" ? "Email or password is wrong." : err.message);
      return;
    }
    router.replace("/console");
    router.refresh();
  }

  return (
    <>
    <form onSubmit={submit} className="mt-6 space-y-3 rounded-xl border border-line bg-surface p-5">
      <label className="block text-sm">
        <span className="text-muted">Email</span>
        <input
          type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        <span className="text-muted">Password</span>
        <input
          type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-bg px-3 py-2"
        />
      </label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <button disabled={busy} className="w-full rounded-md bg-signal px-3 py-2 font-medium text-white disabled:opacity-60">
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
    <DemoPanel demos={demos} picked={picked} onPick={pick} />
    </>
  );
}
