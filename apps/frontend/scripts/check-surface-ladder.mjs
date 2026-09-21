#!/usr/bin/env node
/**
 * Surface-ladder guard.
 *
 * `bg-surface-raised` was a compat alias that pointed at PANEL — so its name
 * promised a raised level while it painted the chrome colour, and every place
 * that reached for it landed one rung below where the name said. Content cards
 * built with it ended up flush with the header instead of sitting above the
 * canvas.
 *
 * Both fill aliases are now fully migrated:
 *
 *   bg-surface-raised[/NN]  ->  bg-card   (or bg-raised when nested in a card)
 *   bg-surface              ->  bg-canvas
 *
 * The `surface.border` and `surface.muted` aliases stay — those are still at
 * ~1.9k call sites and their names do not lie about elevation.
 *
 * Banning the fill aliases here rather than only deleting them from the config
 * matters because an undefined Tailwind class generates nothing silently: a
 * component would go transparent with no error. This fails loudly instead.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const BANNED = [
  {
    re: /\bbg-surface-raised(?:\/\d+)?\b/g,
    hint: "use bg-card for a content card, bg-raised when it nests inside one",
  },
  {
    re: /\bbg-surface(?![-\w])/g,
    hint: "use bg-canvas",
  },
];

export async function checkSurfaceLadder() {
  const findings = [];
  for await (const file of walk(SRC)) {
    const text = await readFile(file, "utf8");
    const issues = [];
    for (const { re, hint } of BANNED) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text)) !== null) {
        issues.push({
          line: text.slice(0, m.index).split("\n").length,
          token: m[0],
          hint,
        });
      }
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
  const { ok, findings } = await checkSurfaceLadder();
  if (!ok) {
    const total = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[surface-ladder] ${total} use(s) of a misleading surface fill alias in ${findings.length} file(s).`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) {
        console.error(`    L${i.line} ${i.token} — ${i.hint}`);
      }
      if (issues.length > 8) console.error(`    … +${issues.length - 8} more`);
    }
    console.error(
      "\n[surface-ladder] Elevation ladder: bg-canvas < bg-panel (chrome) < bg-card < bg-raised."
    );
    process.exit(1);
  }
  console.log("[surface-ladder] OK — no misleading surface fill aliases in src/.");
}

const isMain =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
