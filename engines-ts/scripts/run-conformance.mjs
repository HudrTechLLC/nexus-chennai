// Runs each engine's OFFICIAL Meterless conformance suite, unchanged, against the
// vendored reference, and writes the evidence to logs/conformance_<engine>.txt:
// a header (source commit, file hashes, node version, exact command), the runner's
// raw output, then its exit code. Nothing is edited after capture.
//
//   node engines-ts/scripts/run-conformance.mjs            # all three
//   node engines-ts/scripts/run-conformance.mjs hmem       # one
//
// Exit code: 0 when every suite exits 0, otherwise 1.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const enginesDir = path.resolve(here, "..");
const repoRoot = path.resolve(enginesDir, "..");
const logsDir = path.join(repoRoot, "logs");
const SOURCE = "github.com/Meterless/Meterless @ 1742dec56a66e58eef9dda2d2b865823758ca8cd (Apache-2.0)";
const ENGINES = { "world-model": "world_model", hmem: "hmem", markovian: "markovian" };

// Hashes are over LF-normalised bytes, so a Windows checkout (CRLF) and CI (LF) agree,
// and they match the upstream git blobs' content.
function sha256(file) {
  const CRLF = String.fromCharCode(13, 10);
  const LF = String.fromCharCode(10);
  const bytes = fs.readFileSync(file).toString("latin1").replaceAll(CRLF, LF);
  return createHash("sha256").update(Buffer.from(bytes, "latin1")).digest("hex");
}

function filesUnder(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...filesUnder(full));
    else out.push(full);
  }
  return out.sort();
}

function treeHash(dir) {
  const h = createHash("sha256");
  for (const f of filesUnder(dir)) h.update(path.relative(dir, f).replaceAll("\\", "/") + "\0" + sha256(f) + "\n");
  return h.digest("hex");
}

const wanted = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(ENGINES);
fs.mkdirSync(logsDir, { recursive: true });
let failed = 0;

for (const engine of wanted) {
  if (!(engine in ENGINES)) {
    console.error(`unknown engine ${engine}; expected one of ${Object.keys(ENGINES).join(", ")}`);
    process.exit(2);
  }
  const refDir = path.join(enginesDir, engine, "reference");
  const confDir = path.join(enginesDir, engine, "conformance");
  const tsx = path.join(refDir, "node_modules", "tsx", "dist", "cli.mjs");
  const args = [tsx, "../conformance/runner.ts"];
  const result = spawnSync(process.execPath, args, { cwd: refDir, encoding: "utf-8", env: { ...process.env } });
  const code = result.status ?? 1;
  const header = [
    `# Meterless ${engine} conformance run (official suite, unchanged)`,
    `source:            ${SOURCE}`,
    `runner sha256 LF:  ${sha256(path.join(confDir, "runner.ts"))}`,
    `conformance tree:  ${treeHash(confDir)}`,
    `reference tree:    ${treeHash(refDir)}`,
    `node:              ${process.version} (${process.platform}/${process.arch})`,
    `cwd:               engines-ts/${engine}/reference`,
    `command:           node node_modules/tsx/dist/cli.mjs ../conformance/runner.ts  (= npx tsx ../conformance/runner.ts)`,
    `tsx:               ${JSON.parse(fs.readFileSync(path.join(refDir, "node_modules", "tsx", "package.json"), "utf-8")).version}`,
    `started (UTC):     ${new Date().toISOString()}`,
    "",
    "----- runner output (stdout, then stderr) -----",
  ].join("\n");
  const body = (result.stdout ?? "") + (result.stderr ? `\n[stderr]\n${result.stderr}` : "");
  const footer = `----- end of runner output -----\nexit code: ${code}${result.error ? ` (spawn error: ${result.error.message})` : ""}\n`;
  const file = path.join(logsDir, `conformance_${ENGINES[engine]}.txt`);
  fs.writeFileSync(file, `${header}\n${body.replace(/\s+$/, "")}\n${footer}`, "utf-8");
  const summary = (result.stdout ?? "").trim().split("\n").pop();
  console.log(`${engine}: exit ${code} :: ${summary} -> ${path.relative(repoRoot, file)}`);
  if (code !== 0) failed++;
}
process.exit(failed ? 1 : 0);
