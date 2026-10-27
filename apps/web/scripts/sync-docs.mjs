// Build-time copy of engg/docs into the web app (runs before `next dev` / `next build`).
// - Splits SPEC.md into its 16 tabs at the `<a id="..."></a>` anchors.
// - Copies the other project notes, the diagrams and workstreams.json.
// engg/docs stays the single source of truth; content/ and public/engg-docs/ are generated.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, "..");
const docs = path.resolve(web, "../../engg/docs");
const outContent = path.join(web, "content");
const outPublic = path.join(web, "public", "engg-docs");

if (!fs.existsSync(path.join(docs, "SPEC.md"))) {
  console.error(`sync-docs: ${docs}/SPEC.md not found`);
  process.exit(1);
}

fs.rmSync(outContent, { recursive: true, force: true });
fs.rmSync(outPublic, { recursive: true, force: true });
fs.mkdirSync(path.join(outContent, "spec"), { recursive: true });
fs.mkdirSync(path.join(outContent, "notes"), { recursive: true });
fs.mkdirSync(path.join(outPublic, "diagrams"), { recursive: true });

const stripFrontmatter = (s) => s.replace(/^---\n[\s\S]*?\n---\n/, "");

// ---- spec tabs ----
const TAB_LABELS = {
  overview: "Overview", products: "Products", "claude-code": "Claude Code", requirements: "Requirements",
  architecture: "Architecture", data: "Data", sponsors: "Agents & sponsors", linking: "Linking",
  screens: "Screens & URLs", api: "API", database: "Database", security: "Security",
  phases: "Phases", deliverables: "Deliverables", demo: "Demo", risks: "Risks",
};
const spec = stripFrontmatter(fs.readFileSync(path.join(docs, "SPEC.md"), "utf8").replace(/\r\n/g, "\n"));
const chunks = spec.split(/<a id="([a-z-]+)"><\/a>/);
const tabs = [];
for (let i = 1; i < chunks.length; i += 2) {
  const id = chunks[i];
  const body = chunks[i + 1].replace(/\n---\s*$/, "").trim();
  const part = (body.match(/^# (.+)$/m) || [, TAB_LABELS[id] || id])[1];
  fs.writeFileSync(path.join(outContent, "spec", `${id}.md`), body + "\n");
  tabs.push({ id, label: TAB_LABELS[id] || id, title: part });
}
if (tabs.length !== 16) {
  console.error(`sync-docs: expected 16 spec tabs, found ${tabs.length}`);
  process.exit(1);
}

// ---- project notes ----
// The published notes live in docs-notes.json, which lib/__tests__/docsLinks.test.ts also reads to check
// that every link between notes lands on a page. A note linked from another note must be listed there.
const NOTES = JSON.parse(fs.readFileSync(path.join(here, "docs-notes.json"), "utf8"));
const notes = [];
for (const [file, label] of NOTES) {
  const src = path.join(docs, `${file}.md`);
  if (!fs.existsSync(src)) {
    console.error(`sync-docs: ${file}.md is listed in docs-notes.json but not found`);
    process.exit(1);
  }
  const slug = file.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  fs.writeFileSync(path.join(outContent, "notes", `${slug}.md`), stripFrontmatter(fs.readFileSync(src, "utf8").replace(/\r\n/g, "\n")));
  notes.push({ slug, file: `${file}.md`, label });
}

// ---- diagrams + tracker ----
for (const f of fs.readdirSync(path.join(docs, "diagrams"))) {
  fs.copyFileSync(path.join(docs, "diagrams", f), path.join(outPublic, "diagrams", f));
}
fs.copyFileSync(path.join(docs, "workstreams.json"), path.join(outContent, "workstreams.json"));

fs.writeFileSync(
  path.join(outContent, "index.json"),
  JSON.stringify({ tabs, notes, builtAt: new Date().toISOString() }, null, 2),
);
// ---- eval report (LNK-10, WS2-14) ----
// Committed by the agents lane at output_examples/eval_report.json. Always write the file so the
// static import in lib/evalReport.data.ts resolves; the placeholder means "not committed yet".
const evalSrc = path.resolve(web, "../../output_examples/eval_report.json");
const hasEval = fs.existsSync(evalSrc);
fs.writeFileSync(
  path.join(outContent, "eval_report.json"),
  hasEval ? fs.readFileSync(evalSrc, "utf8") : JSON.stringify({ available: false }) + "\n",
);

// ---- receipt matches (completion ids matched to signed Nightshift receipts; scripts/receipt_matches.py) ----
// Ids only. Always written so lib/receipts.ts resolves; with no file every id reads "not yet matched".
const matchSrc = path.resolve(web, "../../logs/receipt_matches.json");
const hasMatches = fs.existsSync(matchSrc);
fs.writeFileSync(
  path.join(outContent, "receipt_matches.json"),
  hasMatches ? fs.readFileSync(matchSrc, "utf8") : JSON.stringify({ checked: 0, verified: 0, not_verified: 0, ids: [] }) + "\n",
);

console.log(`sync-docs: ${tabs.length} spec tabs, ${notes.length} notes, eval report ${hasEval ? "copied" : "absent"}, receipt matches ${hasMatches ? "copied" : "absent"}`);
