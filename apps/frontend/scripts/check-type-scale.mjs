#!/usr/bin/env node
/**
 * Type-scale guard.
 *
 * Arbitrary `text-[Npx]` sizes are how the UI drifted to six different font
 * sizes below the readability floor. The scale lives in tailwind.config.js; this
 * check keeps call sites on it.
 *
 * Relative units (em/rem/%) are allowed on purpose: inline code at 0.9em of its
 * surrounding text is correct typography, and pinning it to a fixed px would
 * break that relationship.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".ts", ".jsx", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

/** Absolute px font sizes are the banned form. */
const ARBITRARY_PX = /text-\[\s*\d+(?:\.\d+)?px\s*\]/g;

export const SCALE = [
  ["text-display", "20/28 · 600"],
  ["text-title", "16/24 · 600"],
  ["text-body", "14/22 · 400"],
  ["text-label", "12/16 · 500"],
  ["text-meta", "11/14 · 400"],
];

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(p);
      continue;
    }
    if (!SCAN_EXT.some((e) => p.endsWith(e))) continue;
    if (SKIP.some((re) => re.test(p))) continue;
    yield p;
  }
}

export async function checkTypeScale() {
  const findings = [];
  for await (const file of walk(SRC)) {
    const text = await readFile(file, "utf8");
    const issues = [];
    let lineNo = 0;
    for (const line of text.split("\n")) {
      lineNo++;
      ARBITRARY_PX.lastIndex = 0;
      if (!ARBITRARY_PX.test(line)) continue;
      issues.push({
        line: lineNo,
        snippet: line.trim().slice(0, 140),
      });
    }
    if (issues.length) findings.push({ file: relative(ROOT, file), issues });
  }
  return { ok: findings.length === 0, findings };
}

async function main() {
  const { ok, findings } = await checkTypeScale();
  if (!ok) {
    const total = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[type-scale] ${total} arbitrary px font size(s) in ${findings.length} file(s).`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} ${i.snippet}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
    console.error("\n[type-scale] Use the scale from tailwind.config.js instead:");
    for (const [cls, spec] of SCALE) {
      console.error(`    ${cls.padEnd(13)} ${spec}`);
    }
    console.error(
      "\n[type-scale] Relative units (em/rem/%) stay allowed for inline code."
    );
    process.exit(1);
  }
  console.log("[type-scale] OK — no arbitrary px font sizes outside the scale.");
}

const isMain =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
