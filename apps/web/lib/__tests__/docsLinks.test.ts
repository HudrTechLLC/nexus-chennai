/**
 * Every markdown link between engg/docs notes must land on a page of the public /docs site.
 *
 * The site publishes only the notes listed in scripts/docs-notes.json. A note linked from another
 * note but missing from that list used to fall through as a raw `.md` path and 404 (ten did, found
 * in the pre-public audit, 27 Oct). This test reads the same list and the real notes, so a new
 * unlisted link fails CI instead of the live site. Links that leave engg/docs go to GitHub, and the
 * file they name must exist.
 */

import fs from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";
import { REPO_BLOB, rewriteHref, type DocsIndex } from "../docs";

const web = path.resolve(__dirname, "../..");
const repo = path.resolve(web, "../..");
const docs = path.join(repo, "engg/docs");
const NOTES: [string, string][] = JSON.parse(fs.readFileSync(path.join(web, "scripts/docs-notes.json"), "utf8"));

// Same slug rule as scripts/sync-docs.mjs.
const slugOf = (file: string) => file.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const spec = fs.readFileSync(path.join(docs, "SPEC.md"), "utf8");
const index: DocsIndex = {
  tabs: Array.from(spec.matchAll(/<a id="([a-z-]+)"><\/a>/g)).map((m) => ({ id: m[1], label: m[1], title: m[1] })),
  notes: NOTES.map(([file, label]) => ({ slug: slugOf(file), file: `${file}.md`, label })),
  builtAt: "test",
};
const slugs = new Set(index.notes.map((n) => n.slug));
const tabs = new Set(index.tabs.map((t) => t.id));

/** Relative links to markdown notes (code/data links point at the repo, not the site). */
function noteLinks(md: string): string[] {
  return Array.from(md.matchAll(/\]\(([^)\s]+)\)/g))
    .map((m) => m[1])
    .filter((h) => !/^(https?:|mailto:|#)/.test(h) && /\.md(#|$)/.test(h));
}

describe("docs-notes.json", () => {
  it("lists only notes that exist", () => {
    for (const [file] of NOTES) expect(fs.existsSync(path.join(docs, `${file}.md`)), file).toBe(true);
  });

  it("has unique slugs", () => {
    expect(slugs.size).toBe(NOTES.length);
  });
});

describe("links between published notes", () => {
  for (const file of [...NOTES.map(([f]) => f), "SPEC"]) {
    it(`${file}.md: every note link resolves to a /docs page`, () => {
      const md = fs.readFileSync(path.join(docs, `${file}.md`), "utf8");
      const broken = noteLinks(md).filter((href) => {
        const out = rewriteHref(href, index, `${file}.md`) ?? "";
        if (out.startsWith(`${REPO_BLOB}/`)) return !fs.existsSync(path.join(repo, out.slice(REPO_BLOB.length + 1).split("#")[0]));
        const note = out.match(/^\/docs\/notes\/([^/#]+)$/);
        if (note) return !slugs.has(note[1]);
        const tab = out.match(/^\/docs\/([^/#]+)$/);
        if (tab) return !(tabs.has(tab[1]) || tab[1] === "progress");
        return true; // left as a raw .md path: 404 on the site
      });
      expect(broken).toEqual([]);
    });
  }
});
