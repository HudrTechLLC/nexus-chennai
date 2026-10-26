import Link from "next/link";

const cards = [
  { href: "/appeals", title: "Police appeals", body: "Incidents the police have asked the public for help with." },
  { href: "/map", title: "Crime map", body: "Recent crime by area. Locations are grouped into hexagons, never exact." },
  { href: "/tip", title: "Send a tip", body: "Share what you saw, or CCTV footage, without giving your identity." },
];

export default function Home() {
  return (
    <div className="grid gap-8">
      <section>
        <p className="font-mono text-xs uppercase tracking-widest text-accent">Greater Chennai</p>
        <h1 className="mt-1 text-4xl font-bold">Help connect the cases</h1>
        <p className="mt-3 max-w-prose text-muted">
          Nexus helps police stations across Chennai spot crimes that are related, and lets the public help
          safely and anonymously.
        </p>
      </section>
      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <Link key={c.href} href={c.href} className="rounded-xl border border-line bg-surface p-5 hover:border-signal">
            <h2 className="text-lg font-semibold">{c.title}</h2>
            <p className="mt-1 text-sm text-muted">{c.body}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
