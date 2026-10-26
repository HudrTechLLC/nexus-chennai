import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import Link from "next/link";
import { getIndex, rewriteHref } from "@/lib/docs";

/** Renders an engg/docs Markdown note with repo links mapped to app routes. */
export function Markdown({ source }: { source: string }) {
  const index = getIndex();
  return (
    <div className="prose prose-slate max-w-none dark:prose-invert prose-headings:scroll-mt-32 prose-a:text-signal prose-code:before:content-none prose-code:after:content-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug]}
        components={{
          a: ({ href, children }) => {
            const to = rewriteHref(href, index);
            if (to?.startsWith("/")) return <Link href={to}>{children}</Link>;
            const external = !!to && !to.startsWith("#");
            return (
              <a href={to} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined}>
                {children}
              </a>
            );
          },
          img: ({ src, alt }) => {
            const to = rewriteHref(typeof src === "string" ? src : undefined, index);
            return (
              <a href={to} target="_blank" rel="noreferrer" title="Open full size">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={to} alt={alt || "diagram"} className="mx-auto rounded-lg border border-line bg-white p-3" />
              </a>
            );
          },
          table: ({ children }) => (
            <div className="not-prose my-4 overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[560px] border-collapse text-left text-sm [&_td]:border-t [&_td]:border-line [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_th]:bg-bg [&_th]:px-3 [&_th]:py-2 [&_th]:font-mono [&_th]:text-xs [&_th]:uppercase [&_th]:text-muted">
                {children}
              </table>
            </div>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
