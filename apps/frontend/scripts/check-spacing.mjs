#!/usr/bin/env node
/**
 * Spacing guard (ratchet).
 *
 * Every spacing utility must sit on the named ramp defined in
 * tailwind.config.js: hair/tight/snug/base/firm/soft/wide/roomy/broad/deep/
 * page/grand. A numeric step like `p-7` is off-ramp and fails.
 *
 * Three values are allowed as-is because they are statements, not ramp
 * positions:
 *
 *   0    "explicitly zero" — resetting inherited padding is a claim, not a
 *        density choice.
 *   px   Tailwind's built-in 1px, used for hairline icon-button insets
 *        where the ramp's smallest step (2px) would be wrong.
 *   auto `mx-auto` centring, `grow`-style distribution. Not spacing at all.
 *
 * The eight one-off values above 48px (28/56/64/80/96px) are recorded in
 * scripts/spacing-baseline.json rather than named. Naming a token per
 * singleton would make the ramp worse than carrying the debt.
 *
 * Ratchet rather than hard allow-list because that baseline is non-zero. The
 * radius guard is hard because that migration reached 100 %; this one did not.
 *
 * Scanning goes through scripts/spacing-scan.mjs, which handles both the
 * directly-attached direction letters (`mt-2`, not `m-t`) and classes hidden
 * inside nested quoted strings in template interpolations. A guard that
 * missed the latter would let `className={`x ${a ? "p-9" : ""}`}` through
 * untouched, which makes it decoration.
 *
 * Run with --update to re-record the baseline after an intentional
 * migration; new off-ramp values fail.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spacingTokens, NAMED, ZERO, PX, AUTO } from "./spacing-scan.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "spacing-baseline.json");

const SCAN_EXT = [".tsx", ".jsx", ".ts", ".js"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const AS_IS = new Set([ZERO, PX, AUTO]);

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function checkSpacing() {
  let tolerated = new Set();
  try {
    const baseline = JSON.parse(await readFile(BASELINE, "utf8"));
    tolerated = new Set(baseline.classes ?? []);
  } catch {
    tolerated = new Set();
  }
  const violations = [];
  let checked = 0;
  let onRamp = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const [tok, value] of spacingTokens(src)) {
      checked += 1;
      if (NAMED.has(value)) {
        onRamp += 1;
        continue;
      }
      if (AS_IS.has(value)) continue;
      const key = `${rel}::${tok}`;
      if (tolerated.has(key)) continue;
      violations.push({ file: rel, tok, value });
    }
  }

  // A scanner whose value capture is broken reads nothing as on-ramp. If the
  // tree has spacing but the ramp count is zero, the scanner is broken, not
  // the code — and failing loudly here is what stops a following --update
  // from silently baselining the whole ramp.
  if (checked > 100 && onRamp === 0) {
    throw new Error(
      `spacing-scan matched ${checked} classes but 0 on the named ramp — scanner bug, refusing to report`
    );
  }
  return { violations, checked, onRamp, tolerated: tolerated.size };
}

async function update() {
  const classes = {};
  let onRamp = 0;
  let checked = 0;
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const [tok, value] of spacingTokens(src)) {
      checked += 1;
      if (NAMED.has(value)) {
        onRamp += 1;
        continue;
      }
      if (AS_IS.has(value)) continue;
      classes[`${rel}::${tok}`] = true;
    }
  }
  if (checked > 100 && onRamp === 0) {
    throw new Error(
      `spacing-scan matched ${checked} classes but 0 on the named ramp — scanner bug, refusing to record`
    );
  }
  const keys = Object.keys(classes).sort();
  await writeFile(
    BASELINE,
    JSON.stringify(
      {
        classes: keys,
        note: "Off-ramp spacing classes tolerated until someone decides what they should be. Re-record with --update after an intentional migration; new ones fail.",
      },
      null,
      2
    ) + "\n"
  );
  console.log(`[spacing] recorded ${keys.length} tolerated classes`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => { console.error(e); process.exit(1); });
  } else {
    checkSpacing()
      .then(({ violations, checked, onRamp, tolerated }) => {
        if (violations.length) {
          console.error(`[spacing] FAILED - ${violations.length} new off-ramp spacing class(es):`);
          for (const v of violations.slice(0, 25)) {
            console.error(`  ${v.file}: ${v.tok}  (${v.value} has no ramp step)`);
          }
          if (violations.length > 25) console.error(`  … und ${violations.length - 25} weitere`);
          console.error(
            "\nUse a named step from tailwind.config.js: hair(2) tight(4) snug(6) base(8) firm(10) soft(12) wide(16) roomy(20) broad(24) deep(32) page(40) grand(48)."
          );
          process.exit(1);
        }
        console.log(
          `[spacing] OK - ${checked} spacing classes checked, ${onRamp} on the named ramp, ${tolerated} baselined, no new drift`
        );
      })
      .catch((e) => { console.error(e); process.exit(1); });
  }
}
