#!/usr/bin/env node
/**
 * Field-surface guard.
 *
 * Form controls used to carry bg-black/20, /30, /40 and bg-neutral-950
 * interchangeably — three visually different "field" shades depending on who
 * wrote the row. They are now bg-field, which reads as inset against canvas,
 * panel and card alike. An alpha fill cannot do that: the same /20 goes
 * invisible over canvas and muddy over card.
 *
 * Hover/active overlays (hover:bg-white/5 and friends) are not covered — those
 * are transient layers, not the field's own surface.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const CONTROL = /<(input|select|textarea)\b[^>]*?>/gs;
const CLASS_ATTR = /className="([^"]*)"/;
const BAD_FILL = /\bbg-(?:black\/\d+|neutral-950)\b/;

export async function checkFieldSurface() {
  const findings = [];
  for await (const file of walk(SRC)) {
    const text = await readFile(file, "utf8");
    const issues = [];
    CONTROL.lastIndex = 0;
    let m;
    while ((m = CONTROL.exec(text)) !== null) {
      const snip = m[0];
      const cm = CLASS_ATTR.exec(snip);
      if (!cm || !BAD_FILL.test(cm[1])) continue;
      issues.push({
        line: text.slice(0, m.index).split("\n").length,
        tag: m[1],
        snippet: snip.replace(/\s+/g, " ").slice(0, 140),
      });
    }
    if (issues.length) findings.push({ file: relative(ROOT, file), issues });
  }
  return { ok: findings.length === 0, findings };
}

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

async function main() {
  const { ok, findings } = await checkFieldSurface();
  if (!ok) {
    const total = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[field-surface] ${total} form control(s) with an ad-hoc dark fill in ${findings.length} file(s).`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} <${i.tag}> ${i.snippet}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
    console.error(
      "\n[field-surface] Use bg-field (or the TextInput/TextArea/Select components in src/ui/Field.tsx)."
    );
    process.exit(1);
  }
  console.log("[field-surface] OK — every form control sits on bg-field.");
}

const isMain =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
