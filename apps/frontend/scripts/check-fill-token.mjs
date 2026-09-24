#!/usr/bin/env node
/**
 * Fill-token guard (ratchet).
 *
 * The fill dimension was the one nobody was watching. `check-ink-color` guards
 * text, `check-border-token` guards hairlines — but `bg-*` carried no guard at
 * all, and 482 palette-hue fills accumulated. That is how the same "running"
 * state ended up as `bg-sky-950/40` in one file and `bg-amber-600/25` in
 * another, and how a chip's fill and its text colour could drift apart until the
 * pair was unreadable.
 *
 * A fill is a semantic decision, not a colour choice. `bg-danger-subtle` says
 * what is wrong; `bg-red-950/30` only says what hex was typed.
 *
 * Allow-list, read from tailwind.config.js at runtime: every name in
 * theme.extend.colors is legal, plus white/black scrims. The palette hue list
 * comes from `tailwindcss/colors.js`, also at runtime — a guard that keeps its
 * own copy of either list goes quiet when the real one changes.
 *
 * The variant-prefix chain must be admitted. Anchoring on whitespace alone made
 * `hover:bg-sky-600/25` invisible; 206 prefixed palette classes sat in the
 * tree while a naive matcher reported none of them. Same defect family as the
 * ink guard's missing `/` for opacity modifiers.
 *
 * Ratchet rather than hard because the migration is in progress. Tolerated
 * fills live in scripts/fill-baseline.json; new ones fail immediately.
 *
 * Run with --update to re-record after an intentional migration.
 * Run with --explain to print the hue distribution without failing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import colors from "tailwindcss/colors.js";
import config from "../tailwind.config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "fill-baseline.json");

// Flip to true once the baseline is empty, making this a clean-room check.
const HARD = false;

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Semantic colour names come from the config, not a copy.
const TOKENS = new Set(Object.keys(config.theme.extend.colors));

// Scrims and veils are legitimate fills and stay out of the violation set.
const SCRIMS = new Set(["white", "black"]);

// Palette hues come from Tailwind itself.
const PALETTE = Object.keys(colors).filter(
  (k) => !["inherit", "current", "transparent", ...SCRIMS].includes(k)
);
const PALETTE_ALT = PALETTE.sort().join("|");

// Group 1 = full class with its variant chain, group 2 = the hue.
const FILL_RE = new RegExp(
  `(?:^|[^A-Za-z0-9-])((?:[a-zA-Z0-9-]+:)*bg-(${PALETTE_ALT})-[0-9]{2,3}(?:/[0-9]{1,3})?)(?![a-z0-9-])`,
  "g"
);

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

/**
 * Pure scan of one source string. Exported so the matcher's own coverage is
 * testable: every blind spot here is a silent undercount, and the only way to
 * catch "the guard stopped seeing the thing it guards" is to assert the
 * population, not just the verdict.
 */
export function scanFills(src) {
  const fills = [];
  FILL_RE.lastIndex = 0;
  let m;
  while ((m = FILL_RE.exec(src)) !== null) {
    fills.push({ cls: m[1], hue: m[2] });
  }
  return fills;
}

export async function checkFillToken() {
  let baseline = {};
  try {
    baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  } catch {
    baseline = {};
  }

  const findings = [];
  const current = {};
  const hueCount = new Map();
  let total = 0;

  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file);
    const text = await readFile(file, "utf8");
    const lines = text.split("\n");
    const here = new Set();
    const fresh = [];
    for (const f of scanFills(text)) {
      total += 1;
      hueCount.set(f.hue, (hueCount.get(f.hue) ?? 0) + 1);
      here.add(f.cls);
      const allowed = new Set(baseline[rel] ?? []);
      if (!allowed.has(f.cls)) {
        const line = lines.findIndex((l) => l.includes(f.cls)) + 1;
        fresh.push({ line, cls: f.cls, hue: f.hue });
      }
    }
    if (here.size) current[rel] = [...here].sort();
    if (fresh.length) findings.push({ file: rel, issues: fresh });
  }

  return { ok: findings.length === 0, findings, current, hueCount, total };
}

async function main() {
  const { ok, findings, current, hueCount, total } = await checkFillToken();

  if (process.argv.includes("--update")) {
    await writeFile(BASELINE, JSON.stringify(current, null, 2) + "\n", "utf8");
    const n = Object.values(current).reduce((a, v) => a + v.length, 0);
    console.log(
      `[fill] baseline re-recorded: ${n} tolerierte Fill(s) in ${Object.keys(current).length} Datei(en).`
    );
    return;
  }

  if (process.argv.includes("--explain")) {
    console.log(`[fill] ${PALETTE.length} Paletten-Hues · ${total} Paletten-Fills`);
    console.log(`[fill] erlaubt (aus tailwind.config.js): ${[...TOKENS].join(", ")}`);
    console.log("[fill] Hue-Verteilung:");
    for (const [h, n] of [...hueCount.entries()].sort((a, b) => b[1] - a[1]))
      console.log(`  ${String(n).padStart(4)}  ${h}`);
    return;
  }

  if (!ok) {
    const totalNew = findings.reduce((n, f) => n + f.issues.length, 0);
    console.error(
      `[fill] ${totalNew} neue Paletten-Fill(s) in ${findings.length} Datei(en) — kein semantisches Token, nicht in der Baseline.`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8)) console.error(`    L${i.line} ${i.cls}`);
      if (issues.length > 8) console.error(`    … +${issues.length - 8} mehr`);
    }
    console.error("\n[fill] Ein Fill ist eine semantische Entscheidung: bg-danger-subtle sagt, was falsch ist — bg-red-950/30 sagt nur, welcher Hex getippt wurde.");
    console.error("[fill] Bewusste Migration? node scripts/check-fill-token.mjs --update");
    process.exit(1);
  }
  console.log(
    `[fill] OK - ${total} Paletten-Fills geprüft, keine neue Drift über die aufgezeichnete Baseline.`
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
