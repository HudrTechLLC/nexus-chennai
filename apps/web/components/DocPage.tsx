import Link from "next/link";
import { Markdown } from "@/components/Markdown";
import { getHeadings, getNeighbours } from "@/lib/docs";

/** A docs page: content, an "On this page" list on wide screens, and previous / next links. */
export function DocPage({ href, eyebrow, source, file }: { href: string; eyebrow: string; source: string; file?: string }) {
  const headings = getHeadings(source).filter((h) => h.depth === 2);
  const { prev, next } = getNeighbours(href);
  return (
    <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_220px] xl:gap-10">
      <article className="min-w-0 max-w-[900px]">
        <p className="mb-3 font-mono text-xs uppercase tracking-widest text-accent">{eyebrow}</p>
        <Markdown source={source} from={file} />
        <nav aria-label="Previous and next" className="mt-12 grid gap-3 border-t border-line pt-6 sm:grid-cols-2">
          {prev ? (
            <Link href={prev.href} className="rounded-lg border border-line bg-surface p-4 hover:border-signal">
              <span className="block font-mono text-[11px] uppercase tracking-widest text-muted">Previous</span>
              <span className="font-semibold">{prev.label}</span>
            </Link>
          ) : <span />}
          {next && (
            <Link href={next.href} className="rounded-lg border border-line bg-surface p-4 text-right hover:border-signal">
              <span className="block font-mono text-[11px] uppercase tracking-widest text-muted">Next</span>
              <span className="font-semibold">{next.label}</span>
            </Link>
          )}
        </nav>
      </article>
      {headings.length > 1 && (
        <aside className="hidden xl:block">
          <nav aria-label="On this page" className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto">
            <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">On this page</p>
            <ul className="grid gap-1 border-l border-line text-[13px]">
              {headings.map((h) => (
                <li key={h.id}>
                  <a href={`#${h.id}`} className="-ml-px block border-l border-transparent py-0.5 pl-3 text-muted hover:border-ink hover:text-ink">
                    {h.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
      )}
    </div>
  );
}
