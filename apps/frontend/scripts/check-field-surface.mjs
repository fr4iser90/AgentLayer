#!/usr/bin/env node
/**
 * Field-surface guard.
 *
 * Form controls used to carry bg-black/20, /30, /40, bg-[#1a1a1a],
 * bg-surface and bg-surface-raised interchangeably — six visually different
 * "field" shades depending on who wrote the row. They are now bg-field, which
 * reads as inset against canvas, panel and card alike. An alpha fill cannot do
 * that: the same /20 goes invisible over canvas and muddy over card.
 *
 * The rule is allow-list rather than deny-list: a control's own base fill must be
 * bg-field or bg-transparent (for a control that inherits its container's
 * surface, e.g. the chat composer). Anything else fails, so a new ad-hoc shade
 * cannot slip through the way bg-[#1a1a1a] did.
 *
 * Hover/active/focus overlays are not covered — those are transient layers, not
 * the field's own surface.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const CONTROL_START = /<(input|select|textarea)\b/g;
const CLASS_ATTR = /className=(?:"([^"]*)"|\{`([^`]*)`\})/;
const BG_TOKEN = /^bg-[A-Za-z0-9[\]#/.%-]+$/;
const ALLOWED_BASE_FILL = new Set(["bg-field", "bg-transparent"]);

/**
 * End of a JSX tag, scanning past `>` inside expressions.
 *
 * A plain `<input\b[^>]*?>` stops at the `>` of `onChange={(e) => …}`, so the
 * className that follows was never inspected — which is how 74 bg-black/* fields
 * passed a guard that reported "OK".
 */
function tagEnd(src, open) {
  let depth = 0;
  let quote = null;
  for (let i = open + 1; i < src.length; i += 1) {
    const c = src[i];
    if (quote) {
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      quote = c;
    } else if (c === "{") {
      depth += 1;
    } else if (c === "}") {
      depth -= 1;
    } else if (c === ">" && depth === 0) {
      return i + 1;
    }
  }
  return -1;
}

function baseFills(classList) {
  return classList
    .split(/\s+/)
    .filter((t) => t && !t.includes(":") && BG_TOKEN.test(t));
}

export async function checkFieldSurface() {
  const findings = [];
  for await (const file of walk(SRC)) {
    const text = await readFile(file, "utf8");
    const issues = [];
    CONTROL_START.lastIndex = 0;
    let m;
    while ((m = CONTROL_START.exec(text)) !== null) {
      const end = tagEnd(text, m.index);
      if (end === -1) continue;
      const tag = text.slice(m.index, end);
      const cm = CLASS_ATTR.exec(tag);
      if (!cm) continue;
      const classList = cm[1] ?? cm[2] ?? "";
      const bad = baseFills(classList).filter((t) => !ALLOWED_BASE_FILL.has(t));
      if (!bad.length) continue;
      issues.push({
        line: text.slice(0, m.index).split("\n").length,
        tag: m[1],
        fills: bad.join(" "),
        snippet: tag.replace(/\s+/g, " ").slice(0, 140),
      });
      // Do not re-scan inside this tag.
      CONTROL_START.lastIndex = end;
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
      `[field-surface] ${total} form control(s) with an ad-hoc fill in ${findings.length} file(s).`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} <${i.tag}> ${i.fills}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
    console.error(
      "\n[field-surface] A control's own fill must be bg-field or bg-transparent."
    );
    console.error(
      "[field-surface] Prefer the TextInput/TextArea/Select components in src/ui/Field.tsx."
    );
    process.exit(1);
  }
  console.log("[field-surface] OK — every form control sits on bg-field or bg-transparent.");
}

const isMain =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
