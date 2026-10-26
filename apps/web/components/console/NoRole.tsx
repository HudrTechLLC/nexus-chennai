/** Shown to a signed-in account that has no police profile: it sees nothing (spec Part I). */
export function NoRole() {
  return (
    <main className="mx-auto max-w-md px-4 py-16">
      <section className="rounded-xl border border-line bg-surface p-6">
        <h1 className="text-xl font-bold">No police role on this account</h1>
        <p className="mt-2 text-sm text-muted">
          This account is signed in but has no console role. An administrator assigns roles; there is no self sign-up.
        </p>
        <form action="/console/signout" method="post" className="mt-4">
          <button className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-bg">Sign out</button>
        </form>
      </section>
    </main>
  );
}
