#!/usr/bin/env node
/**
 * Radius guard.
 *
 * Hard allow-list, no baseline. The radius codemod landed 1263 of 1266 raw
 * radii onto tokens and the three that were already tokens bring the total to
 * 1266 with nothing left over, so unlike the ink and border guards this one
 * has no existing debt to tolerate. Zero tolerance is affordable exactly where
 * the migration is actually complete; claiming it where it is not would just
 * make the guard red on day one.
 *
 * Allowed sizes: tile (6px) · card (8px) · sheet (12px) · pill (999px),
 * in any directional form (`rounded-t-card`, `rounded-bl-pill`, ...).
 *
 * Rejected: bare `rounded` (Tailwind default 4px, no token), the named
 * defaults sm/md/lg/xl/2xl/3xl, and arbitrary values like `rounded-[7px]`.
 * Bare `rounded` is the one that matters most — it reads like "just the
 * default" rather than "a missing token", which is how 346 of them went
 * unnoticed.
 *
 * Run with --update to record a deliberate exception in
 * scripts/radius-baseline.json.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "radius-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const ALLOWED = new Set(["tile", "card", "sheet", "pill"]);
const DIRECTIONS = new Set(["t", "r", "b", "l", "tl", "tr", "bl", "br"]);

// The hyphen inside the character class is load-bearing — see the border
// guard's note on how a missing one hides every hyphenated class from the
// count. The trailing boundary must also accept the closing quote.
const RADIUS_CLASS =
  /(^|\s|["'`])((?:[a-zA-Z0-9-]+:)*rounded(-[a-z0-9[\]%./-]*)?)(?=[\s"'`]|$)/g;

// `rounded` -> ["", "DEFAULT"]
// `rounded-t-card` -> ["t", "card"]
// `rounded-[7px]` -> ["", "[7px]"]
function parseSize(cls) {
  const noVariant = cls.slice(cls.lastIndexOf(":") + 1);
  if (noVariant === "rounded") return ["", "DEFAULT"];
  const rest = noVariant.replace(/^rounded-/, "");
  const parts = rest.split("-");
  if (parts.length > 1 && DIRECTIONS.has(parts[0])) {
    return [parts[0], parts.slice(1).join("-")];
  }
  return ["", rest];
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function checkRadius() {
  let tolerated = new Set();
  try {
    tolerated = new Set((JSON.parse(await readFile(BASELINE, "utf8")).classes ?? []));
  } catch {
    tolerated = new Set();
  }
  const violations = [];
  let checked = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const m of src.matchAll(RADIUS_CLASS)) {
      const cls = m[2];
      const [, size] = parseSize(cls);
      checked += 1;
      if (ALLOWED.has(size)) continue;
      const key = `${rel}::${cls}`;
      if (tolerated.has(key)) continue;
      const kind =
        size === "DEFAULT"
          ? "bare `rounded` (4px, no token)"
          : /^\[.*\]$/.test(size)
            ? "arbitrary radius"
            : "off-token radius";
      violations.push({ file: rel, cls, kind });
    }
  }
  return { violations, checked, tolerated: tolerated.size };
}

async function update() {
  const classes = {};
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const m of src.matchAll(RADIUS_CLASS)) {
      const [, size] = parseSize(m[2]);
      if (ALLOWED.has(size)) continue;
      classes[`${rel}::${m[2]}`] = true;
    }
  }
  const keys = Object.keys(classes).sort();
  await writeFile(
    BASELINE,
    JSON.stringify(
      { classes: keys, note: "Deliberate off-token radius exceptions. The default is zero: the codemod landed everything." },
      null,
      2
    ) + "\n"
  );
  console.log(`[radius] recorded ${keys.length} tolerated classes`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => { console.error(e); process.exit(1); });
  } else {
    checkRadius()
      .then(({ violations, checked, tolerated }) => {
        if (violations.length) {
          console.error(`[radius] FAILED - ${violations.length} off-token radius class(es):`);
          for (const v of violations.slice(0, 25)) console.error(`  ${v.file}: ${v.cls}  (${v.kind})`);
          if (violations.length > 25) console.error(`  … und ${violations.length - 25} weitere`);
          process.exit(1);
        }
        console.log(
          `[radius] OK - ${checked} radius classes checked, all on tile/card/sheet/pill (${tolerated} baselined)`
        );
      })
      .catch((e) => { console.error(e); process.exit(1); });
  }
}
