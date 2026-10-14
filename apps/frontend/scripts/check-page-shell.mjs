#!/usr/bin/env node
/**
 * PageShell gate — single source of truth for content width.
 *
 * Correct = <PageShell density="…"> (or AdminInterfacesPageShell, which wraps it)
 *           with a density allowed by page-shell-policy.json for that path.
 * Wrong   = missing shell, forbidden density, or DIY `mx-auto max-w-page*`.
 *
 *   npm run lint:page-shell
 *   npm run lint:page-shell:explain
 *   npm run lint:page-shell:update
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGES = join(ROOT, "src", "pages");
const BASELINE = join(__dirname, "page-shell-baseline.json");
const POLICY = join(__dirname, "page-shell-policy.json");

const DENSITIES = new Set(["narrow", "default", "wide", "measure", "dialog", "fill"]);
/** Forbidden DIY page columns (tokens live only inside layout/PageShell.tsx). */
const DIY_PAGE_MAX_RE =
  /className\s*=\s*(?:\{`|["'`])[^"'`]*\bmx-auto\b[^"'`]*\bmax-w-page(?:Narrow|Wide)?\b|\bmax-w-page(?:Narrow|Wide)?\b[^"'`]*\bmx-auto\b/;

const SCAN_EXT = [".tsx"];
const SKIP = [
  /\.test\./,
  /\.snap$/,
  /interfaces\/.*Section/,
  /setup\//,
  /admin\/AdminInterfaces\.tsx$/,
  /admin\/interfaces\/AdminInterfacesPageShell\.tsx$/,
];

function globToRegExp(glob) {
  const esc = glob
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "<<<DS>>>")
    .replace(/\*/g, "[^/]*")
    .replace(/<<<DS>>>/g, ".*");
  return new RegExp(`^${esc}$`);
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

function interesting(rel) {
  const base = rel.split("/").pop() || "";
  return (
    /Page\.tsx$/.test(base) ||
    /Settings\.tsx$/.test(base) ||
    /^src\/pages\/admin\/Admin[^/]+\.tsx$/.test(rel)
  );
}

function extractDensities(src) {
  const out = [];
  for (const m of src.matchAll(/<PageShell\b([^>]*)>/gs)) {
    const attrs = m[1] || "";
    const dm = attrs.match(
      /\bdensity\s*=\s*(?:\{\s*)?["'](narrow|default|wide|measure|dialog|fill)["']/
    );
    out.push(dm ? dm[1] : "default");
  }
  for (const m of src.matchAll(/<AdminInterfacesPageShell\b([^>]*)>/gs)) {
    const attrs = m[1] || "";
    out.push(/(?:^|\s)wide(?:\s|=|$|\/)/.test(attrs) || /\bwide\s*=\s*\{?\s*true/.test(attrs) ? "wide" : "default");
  }
  return out;
}

function policyFor(rel, families) {
  for (const fam of families) {
    for (const g of fam.match || []) {
      if (globToRegExp(g).test(rel)) return fam;
    }
  }
  return null;
}

/** Map legacy baseline token names → densities. */
function normalizeShellToken(raw) {
  if (!raw || raw === "missing") return null;
  const map = {
    pageNarrow: "narrow",
    page: "default",
    pageWide: "wide",
    measure: "measure",
    dialog: "dialog",
    fill: "fill",
    narrow: "narrow",
    default: "default",
    wide: "wide",
  };
  return map[raw] || (DENSITIES.has(raw) ? raw : null);
}

export async function checkPageShells() {
  const policy = JSON.parse(await readFile(POLICY, "utf8"));
  const families = policy.families || [];
  let baseline = {};
  try {
    baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  } catch {
    baseline = {};
  }

  const rows = [];
  const findings = [];
  const current = {};

  for await (const file of walk(PAGES)) {
    const rel = relative(ROOT, file).replaceAll("\\", "/");
    if (!interesting(rel)) continue;
    const src = await readFile(file, "utf8");
    const densities = extractDensities(src);
    const primary = densities[0] || null;
    const via = src.includes("AdminInterfacesPageShell")
      ? "AdminInterfacesPageShell"
      : densities.length
        ? "PageShell"
        : "none";

    rows.push({ file: rel, shell: primary || "missing", via, densities });
    current[rel] = primary || "missing";

    if (!primary) {
      findings.push({
        file: rel,
        issue:
          'missing <PageShell density="…"> (or AdminInterfacesPageShell). Do not invent mx-auto max-w-page*.',
      });
      continue;
    }

    if (DIY_PAGE_MAX_RE.test(src)) {
      findings.push({
        file: rel,
        issue: "raw mx-auto max-w-page* wrapper — use <PageShell density=\"…\"> instead",
      });
    }

    const fam = policyFor(rel, families);
    if (!fam) {
      findings.push({
        file: rel,
        issue:
          "no page-shell-policy family matches this path — add a family in scripts/page-shell-policy.json",
      });
    } else {
      const allowed = new Set(fam.allowed || []);
      for (const d of densities) {
        if (!allowed.has(d)) {
          findings.push({
            file: rel,
            issue: `density "${d}" not allowed for family "${fam.id}" (allowed: ${[...allowed].join(", ")})`,
          });
        }
      }
      if (Array.isArray(fam.forbid)) {
        for (const d of densities) {
          if (fam.forbid.includes(d)) {
            findings.push({
              file: rel,
              issue: `density "${d}" forbidden for family "${fam.id}"`,
            });
          }
        }
      }
    }

    const expected = normalizeShellToken(baseline[rel]);
    if (expected && expected !== primary) {
      findings.push({
        file: rel,
        issue: `shell drifted from baseline ${expected} → ${primary} (via ${via})`,
      });
    }
  }

  return { ok: findings.length === 0, findings, rows, current };
}

async function main() {
  const { ok, findings, rows, current } = await checkPageShells();
  const explain = process.argv.includes("--explain");
  const update = process.argv.includes("--update");

  if (update) {
    const sorted = Object.fromEntries(
      Object.entries(current).sort(([a], [b]) => a.localeCompare(b))
    );
    await writeFile(BASELINE, JSON.stringify(sorted, null, 2) + "\n", "utf8");
    console.log(`[page-shell] baseline re-recorded: ${Object.keys(sorted).length} page(s).`);
    process.exit(0);
  }

  if (explain) {
    const by = new Map();
    for (const r of rows) {
      if (!by.has(r.shell)) by.set(r.shell, []);
      by.get(r.shell).push(`${r.file} (${r.via}${r.densities.length > 1 ? `; densities=${r.densities.join("+")}` : ""})`);
    }
    console.log("[page-shell] inventory (density ← PageShell / policy):");
    for (const shell of [...by.keys()].sort()) {
      console.log(`  ${shell} (${by.get(shell).length})`);
      for (const f of by.get(shell).sort()) console.log(`    ${f}`);
    }
  }

  if (!ok) {
    console.error(`[page-shell] ${findings.length} issue(s):`);
    for (const f of findings) console.error(`  ${f.file}: ${f.issue}`);
    console.error(
      "[page-shell] Fix density / wrap with <PageShell>, or update scripts/page-shell-policy.json"
    );
    process.exit(1);
  }

  console.log(
    `[page-shell] OK — ${rows.length} page(s); densities enforced via page-shell-policy.json` +
      (explain ? "" : " (npm run lint:page-shell:explain)")
  );
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
