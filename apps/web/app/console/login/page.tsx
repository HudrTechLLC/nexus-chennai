import { parseDemoLogins } from "@/lib/demoLogins";
import { LoginForm } from "./LoginForm";

export const metadata = { title: "Police sign-in · Nexus Chennai" };
// read DEMO_LOGINS per request, never baked in at build
export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-16">
      {/* the form stays narrow; the demo tiles below use the full width for one row */}
      <div className="mx-auto max-w-sm">
        <p className="font-mono text-xs uppercase tracking-widest text-accent">Nexus · Police console</p>
        <h1 className="mt-1 text-2xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-muted">Accounts are issued by an administrator. There is no public sign-up.</p>
      </div>
      <LoginForm demos={parseDemoLogins(process.env.DEMO_LOGINS)} />
    </main>
  );
}
