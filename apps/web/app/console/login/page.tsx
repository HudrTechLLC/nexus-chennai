import { LoginForm } from "./LoginForm";

export const metadata = { title: "Police sign-in · Nexus Chennai" };

export default function LoginPage() {
  return (
    <main className="mx-auto max-w-sm px-4 py-16">
      <p className="font-mono text-xs uppercase tracking-widest text-accent">Nexus · Police console</p>
      <h1 className="mt-1 text-2xl font-bold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Accounts are issued by an administrator. There is no public sign-up.</p>
      <LoginForm />
    </main>
  );
}
