#!/usr/bin/env node
/**
 * One-off migration: raw stacking levels onto the named zIndex scale.
 *
 * The role of a floating layer is readable from the class string it sits in,
 * with three exceptions listed below. `absolute`/`sticky` means the layer
 * belongs to its own container; `fixed inset-0` means it covers the page, and a
 * `justify-end`/`items-end` on that layer means it is a sheet anchored to an
 * edge rather than a centred dialog.
 *
 * Run with --dry-run to print the table without writing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// Where the class string alone would have been read wrong. Each of these is a
// layer whose container is not what the positioning word suggests.
const OVERRIDES = {
  // A popover above the embedded chat's input, bounded by that panel — not
  // canvas chrome, even though it shares the dashboard and the old value.
  "features/dashboard/DashboardEmbeddedChat.tsx:1157": "docked",
  // A veil over the composer. The drag veil next to it is `lift` too; the
  // transcribe veil wins by DOM order, which is what it did before.
  "pages/ChatPage.tsx:4110": "lift",
  // A sticky page header on the public share view. No canvas, no blocks.
  "features/dashboard/PublicGalleryShareView.tsx:52": "lift",
};

// Group 1 = variant chain, group 2 = the raw level. `z-auto` is already a token
// and stays. The boundary must not require whitespace: `z-[1]` in
// `relative z-[1] mt-snug` has a bracket on both sides, and an anchor on `\b`
// after the bracket finds nothing because `]` and a space are both non-word.
const Z_RE =
  /(^|[^A-Za-z0-9-])((?:[a-zA-Z0-9-]+:)*z-)(auto|[0-9]+|\[[^\]]+\])(?![A-Za-z0-9-])/g;

function roleFor(rel, lineNo, level, line) {
  const override = OVERRIDES[`${rel}:${lineNo}`];
  if (override) return override;
  if (level === "auto") return null;

  const bare = level.replace(/[[\]]/g, "");
  const covers = line.includes("fixed") && line.includes("inset-0");
  const anchored = line.includes("justify-end") || line.includes("items-end");

  if (level.startsWith("[")) {
    if (bare === "1") return "lift";
    if (bare === "60") return "tooltip";
    if (bare === "80") return "overlay";
    if (bare === "100") return "modal";
    return null; // unknown arbitrary value — a human must say what it is
  }
  switch (bare) {
    case "10":
      return "lift";
    case "20":
      return "canvas";
    case "30":
      return "docked";
    case "40":
      return "chrome";
    case "50":
      if (!covers) return "menu";
      return anchored ? "overlay" : "modal";
    default:
      return null;
  }
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

const dryRun = process.argv.includes("--dry-run");
const rows = [];
const unresolved = [];
let filesChanged = 0;

for await (const file of walk(SRC)) {
  const rel = relative(SRC, file);
  const text = await readFile(file, "utf8");
  const lines = text.split("\n");
  let changed = 0;

  const next = lines.map((line, i) => {
    Z_RE.lastIndex = 0;
    return line.replace(Z_RE, (whole, pre, head, level) => {
      const role = roleFor(rel, i + 1, level, line);
      if (role === null) {
        if (level !== "auto") unresolved.push(`${rel}:${i + 1} z-${level}`);
        return whole;
      }
      changed += 1;
      rows.push(`${rel}:${i + 1}\tz-${level}\t→\tz-${role}`);
      return `${pre}${head}${role}`;
    });
  });

  if (changed && !dryRun) {
    await writeFile(file, next.join("\n"), "utf8");
    filesChanged += 1;
  }
}

for (const r of rows) console.log(r);
console.log(
  `\n[z-codemod] ${rows.length} Stelle(n) migriert${dryRun ? " (dry-run, nichts geschrieben)" : ` in ${filesChanged} Datei(en)`}.`
);
if (unresolved.length) {
  console.error(`[z-codemod] ${unresolved.length} Stelle(n) ohne Rollenregel:`);
  for (const u of unresolved) console.error(`  ${u}`);
  process.exit(1);
}