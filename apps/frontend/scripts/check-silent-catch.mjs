#!/usr/bin/env node
/**
 * Silent-catch guard (ratchet).
 *
 * Measured before this guard: 410 `catch` sites in `apps/frontend/src`, 48 of
 * them swallowing with `.catch(() => {})` or `.catch(() => undefined)`, and
 * `console.error` appearing zero times. Nine of those were `putConversation()`
 * — the user's own message, rendered from local state, absent from the server,
 * gone on reload, with nothing saying so.
 *
 * The rule is not "never swallow". Some of these are right: a fire-and-forget
 * telemetry ping, an abort the user asked for. The rule is that a swallow must
 * not be *groundless* — a `// why:` line above it (or on it) states what is
 * being given up. That turns an unreviewable count into a list of decisions,
 * and the ones without a reason are the ones that stand out.
 *
 * Ratchet rather than zero-tolerance: 37 sites remain, and writing 37 reasons I
 * have not verified would be worse than recording them as debt. Each one gets
 * annotated when its file is next touched; nothing new gets in silently.
 *
 * Run with --update to re-record after an intentional change.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { stripComments } from "./strip-comments.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "silent-catch-baseline.json");

const SCAN_EXT = [".ts", ".tsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

/**
 * `.catch(() => {})`, `.catch(() => undefined)`, `.catch(() => null)`,
 * `.catch(() => noop)`, and the same with a named or typed parameter —
 * `.catch((e) => {})` swallows just as hard as `.catch(() => {})`, and a
 * matcher that only saw the empty-paren form would rate the more common
 * spelling compliant.
 *
 * A `.catch(handler)` where handler is a real function is NOT a swallow — it
 * reports somewhere, which is the whole requirement.
 */
const SILENT_CATCH =
  /\.catch\(\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*(?:\{\s*\}|undefined|null|noop)\s*\)/g;

const WHY = /\bwhy:/;

/**
 * Pure scan. Exported because every matcher in this repo's guard family has
 * failed silently at least once — missing hyphen, missing `/`, missing variant
 * chain, comment text read as code — and a scan reachable only through file
 * I/O cannot be pinned by a test.
 */
export function scanSilentCatches(src) {
  const code = stripComments(src);
  // The reason lives in a comment, so it has to be read from the ORIGINAL
  // source: scanning the blanked copy for `why:` finds nothing and every
  // annotated site still fails, which is a guard that cannot be satisfied.
  // Offsets and newlines survive blanking, so line numbers line up between the
  // two and a comment-only mention of `.catch(() => {})` still cannot register.
  const originalLines = src.split("\n");
  const findings = [];
  for (const m of code.matchAll(SILENT_CATCH)) {
    const line = code.slice(0, m.index).split("\n").length;
    const own = originalLines[line - 1] ?? "";
    const prev = originalLines[line - 2] ?? "";
    if (WHY.test(own) || WHY.test(prev)) continue;
    findings.push({ line, cls: m[0] });
  }
  return findings;
}

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP.some((re) => re.test(full))) continue;
      yield* walk(full);
    } else if (SCAN_EXT.some((ext) => entry.name.endsWith(ext))) {
      yield full;
    }
  }
}

export async function checkSilentCatch() {
  const baseline = JSON.parse(await readFile(BASELINE, "utf8"));
  const tolerated = new Set(baseline.sites ?? []);
  const violations = [];
  let checked = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const finding of scanSilentCatches(src)) {
      checked += 1;
      // Keyed by file + the swallow's text, not by line: a line number moves
      // whenever anything above it changes, and a baseline that fails on
      // unrelated edits gets widened instead of read.
      const key = `${rel}::${finding.cls}`;
      if (tolerated.has(key)) continue;
      violations.push({ file: rel, line: finding.line, cls: finding.cls });
    }
  }
  return { violations, checked, tolerated: tolerated.size };
}

async function update() {
  const sites = {};
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const rel = relative(ROOT, file);
    for (const finding of scanSilentCatches(src)) {
      sites[`${rel}::${finding.cls}`] = true;
    }
  }
  const keys = Object.keys(sites).sort();
  await writeFile(
    BASELINE,
    JSON.stringify(
      {
        note: "Swallowed promise rejections without a `// why:` line. Re-record with --update after an intentional change; new ones fail. Annotate rather than widen where you can.",
        sites: keys,
      },
      null,
      2
    ) + "\n"
  );
  console.log(`[silent-catch] recorded ${keys.length} tolerated swallows`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => {
      console.error(e);
      process.exit(1);
    });
  } else {
    checkSilentCatch()
      .then(({ violations, checked, tolerated }) => {
        if (violations.length) {
          console.error(
            `[silent-catch] FAILED - ${violations.length} groundless swallow(s):`
          );
          for (const v of violations.slice(0, 25)) {
            console.error(`  ${v.file}:${v.line}  ${v.cls}`);
          }
          if (violations.length > 25) {
            console.error(`  … und ${violations.length - 25} weitere`);
          }
          console.error(
            "Add a `// why:` line saying what is given up, or report it."
          );
          process.exit(1);
        }
        console.log(
          `[silent-catch] OK - ${checked} swallowed rejection(s) checked, ${tolerated} baselined, no new drift`
        );
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  }
}