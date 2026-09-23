#!/usr/bin/env node
/**
 * Text-colour codemod: raw Tailwind greys onto the `ink` scale.
 *
 * Fill-aware, deliberately. A blind `text-white` -> `text-ink-primary` would
 * have dimmed white-on-saturated-fill text (e.g. `bg-sky-500 text-white` in
 * ProposalMessageBody, `bg-violet-600 text-white` in VoiceHandsFreeBar) to a
 * token that is not the on-fill token. So each class occurrence is decided by
 * whether the same class string also paints a saturated, opaque fill:
 *
 *   saturated fill present  -> text-ink-on-fill
 *   otherwise              -> luminance mapping
 *
 * Luminance mapping, chosen so no site lands below where it started:
 *   white / neutral-100 / neutral-200 -> ink-primary    (13.22:1 on card)
 *   neutral-300                       -> ink-secondary  ( 8.17:1)
 *   neutral-400                       -> ink-muted      ( 6.75:1)
 *   neutral-500                       -> ink-muted      ( 3.36 -> 6.75, a fix)
 *   neutral-600                       -> ink-faint      ( 2.04 -> 3.47, decorative)
 *
 * Alpha fills (`bg-sky-600/50`) are translucent and composite against the
 * surface underneath; they do not trigger the on-fill branch.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";

const ROOT = process.argv[2] || "src";
const DRY = process.argv.includes("--dry");
const SCAN_EXT = [".tsx", ".ts"];
const SKIP = [/node_modules/];

const LUMINANCE = {
  "text-white": "text-ink-primary",
  "text-neutral-100": "text-ink-primary",
  "text-neutral-200": "text-ink-primary",
  "text-neutral-300": "text-ink-secondary",
  "text-neutral-400": "text-ink-muted",
  "text-neutral-500": "text-ink-muted",
  "text-neutral-600": "text-faint-placeholder",
};
// Kept separate so a typo cannot silently map to a non-existent class.
LUMINANCE["text-neutral-600"] = "text-ink-faint";

// Opaque saturated fills: bg-<hue>-<500|600|700> or our saturated tokens.
//
// The negative lookahead for `/` is load-bearing. Without it `bg-sky-600/80`
// matched via its `hover:bg-sky-500` tail, and near-black ink on an 80 %-alpha
// sky fill composites to 3.45:1 — worse than the white it replaced. Translucent
// fills keep white because white is what actually holds contrast there.
const SATURATED =
  /(?:^|\s)bg-(?:accent|success|warning|danger)(?![-\w/])|(?:^|\s)bg-(?:sky|blue|indigo|violet|purple|fuchsia|pink|rose|red|orange|amber|yellow|lime|green|emerald|teal|cyan)-(?:500|600|700)(?![-\w/])/;

/** Class-string shapes we understand: "..." , `...` , and '...' inside ternaries. */
const CLASS_STRINGS = /"([^"\n]*)"|`([^`\n]*)`|'([^'\n]*)'/g;

function hasClass(list, cls) {
  return new RegExp(`(^|\\s)${cls.replace(/[-/]/g, "\\$&")}(\\s|$)`).test(list);
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

const tally = {};
let filesChanged = 0;

for await (const file of walk(ROOT)) {
  const src = await readFile(file, "utf8");
  let out = "";
  let last = 0;
  let m;
  CLASS_STRINGS.lastIndex = 0;
  while ((m = CLASS_STRINGS.exec(src)) !== null) {
    const raw = m[1] ?? m[2] ?? m[3] ?? "";
    if (!raw || !/text-(white|neutral-)/.test(raw)) continue;
    const onFill = SATURATED.test(raw);
    let next = raw;
    for (const [from, to0] of Object.entries(LUMINANCE)) {
      if (!hasClass(next, from)) continue;
      const to = onFill && from === "text-white" ? "text-ink-on-fill" : to0;
      next = next.replace(
        new RegExp(`(^|\\s)${from.replace(/-/g, "\\-")}(\\s|$)`, "g"),
        `$1${to}$2`
      );
      tally[to] = (tally[to] || 0) + 1;
    }
    if (next !== raw) {
      out += src.slice(last, m.index) + src.slice(m.index, m.index + 1) + next + src[m.index + raw.length + 1];
      last = m.index + raw.length + 2;
    }
  }
  out += src.slice(last);
  if (out !== src) {
    filesChanged += 1;
    if (!DRY) await writeFile(file, out, "utf8");
  }
}

console.log(`${DRY ? "[dry] would change" : "changed"} ${filesChanged} file(s)`);
for (const [k, v] of Object.entries(tally).sort((a, b) => b[1] - a[1])) {
  console.log(`  -> ${k.padEnd(20)} ${v}`);
}
