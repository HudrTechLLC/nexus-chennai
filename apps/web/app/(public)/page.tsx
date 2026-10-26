import Link from "next/link";
import { AppealCard } from "@/components/public/AppealCard";
import { getAppeals } from "@/lib/publicData";

export const revalidate = 60;

const STEPS = [
  { t: "Your browser cleans it", b: "Photos lose their location and camera details before they leave your phone. Faces can be blurred." },
  { t: "We keep almost nothing", b: "No IP address, device, phone number, email or exact time: only the week and, if you choose, an area of about 0.7 km²." },
  { t: "You choose about replies", b: "Stay fully anonymous, or keep a tip code and passphrase to read police replies. Nobody can recover them." },
];

/** Public home (spec G1 /). */
export default async function Home() {
  const { appeals } = await getAppeals();
  return (
    <div className="grid gap-10">
      <p className="rounded-md border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        <strong>Emergency? Call 112.</strong> This site is not monitored around the clock.
      </p>

      <section className="grid gap-6 md:grid-cols-[1.4fr_1fr] md:items-end">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-accent">Greater Chennai</p>
          <h1 className="mt-1 text-4xl font-bold">Help connect the cases</h1>
          <p className="mt-3 max-w-prose text-muted">
            Nexus helps police stations across the city spot crimes that are related, and lets the public help safely and anonymously.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 md:justify-end">
          <Link href="/tip/new" className="rounded-md bg-signal px-5 py-3 font-semibold text-white">Share information anonymously</Link>
          <Link href="/map" className="rounded-md border border-line px-5 py-3">See what&apos;s happening near you</Link>
        </div>
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-2xl font-bold">Latest appeals</h2>
          <Link href="/appeals" className="text-sm underline">All appeals</Link>
        </div>
        {appeals.length === 0 ? (
          <p className="mt-3 rounded-xl border border-dashed border-line p-6 text-center text-muted">No open appeals right now.</p>
        ) : (
          <div className="mt-3 grid gap-4 md:grid-cols-3">{appeals.slice(0, 3).map((a) => <AppealCard key={a.id} a={a} />)}</div>
        )}
      </section>

      <section>
        <h2 className="text-2xl font-bold">How anonymity works</h2>
        <ol className="mt-3 grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <li key={s.t} className="rounded-xl border border-line bg-surface p-5">
              <p className="font-mono text-xs text-accent">STEP {i + 1}</p>
              <h3 className="mt-1 font-semibold">{s.t}</h3>
              <p className="mt-1 text-sm text-muted">{s.b}</p>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-sm"><Link href="/about/privacy" className="underline">Read exactly what is stored and what is not</Link> · <Link href="/tip/status" className="underline">Check a tip</Link> · <Link href="/cctv" className="underline">Shop owners: share CCTV</Link></p>
      </section>
    </div>
  );
}
