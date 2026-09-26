#!/usr/bin/env node
/**
 * Loading-placeholder guard.
 *
 * A loading branch that renders one line of text where a list will be does more
 * than look unfinished: the text is ~22 px, the list behind it is hundreds, so
 * the arrival of the data pushes everything under it down the page. That push is
 * what a skeleton is for — the placeholder stands at the height of the thing it
 * replaces so nothing that is already on screen has to move.
 *
 * The rule is deliberately narrow, because "show a skeleton everywhere" is not a
 * rule, it is churn:
 *
 *  - Only a branch whose *condition* is a loading flag counts. `status ? … : …`
 *    and `busy ? … : …` decide meaning, not readiness, and a skeleton would be
 *    wrong there. A *negated* flag (`&& !loading ? <li>nothing yet</li> : rows`)
 *    does not count either: that text arm is the empty state, and reserving it
 *    would hold room for records that are never coming.
 *  - Only a branch that is *replaced by a repeated structure* counts: the loaded
 *    branch has to render a `.map(`, a `<ul>`/`<ol>` or a `<table>`. A heading,
 *    a form, or a single card that appears where a sentence was inserts content
 *    below the fold instead of moving what is already visible — near-zero shift,
 *    and a placeholder would just add a second shape to paint.
 *  - A branch that already reserves height (`Skeleton*`, `animate-pulse`,
 *    `animate-spin`, `Loader`) is compliant, wherever it got that height from.
 *
 * Converting 23 files in one pass is how a loading state turns into a visual
 * regression hunt, so this is a ratchet:
 * `loading-placeholder-baseline.json` records the count per file and a file may
 * only go down. `--update` lowers the floor after a conversion pass.
 *
 * Two things are deliberately out of reach and are the reviewer's, not the
 * guard's: whether the loaded arm is a list hidden behind a component call
 * (`<TaskList …/>` says nothing about its height), and whether the growth
 * actually moves something — a branch inside a fixed-height scroller, inside a
 * dashboard block (react-grid-layout sizes items from the stored `h`, so the
 * block's box is fixed and `overflow-hidden` clips whatever grows past it), or
 * one whose content is only ever inserted below the fold, shifts nothing and
 * needs no placeholder however bare its text is.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { findTagEnd } from "./jsx-tags.mjs";
import { stripComments } from "./strip-comments.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "loading-placeholder-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/, /\.stories\./];

/** A readiness flag, not a meaning flag. */
const LOADING_NAME =
  /\b(loading|isLoading|initialLoading|booting|fetching|isFetching|syncing|[A-Za-z]*Loading)\b/;
const TERNARY = new RegExp(`${LOADING_NAME.source}[^?\\n]{0,40}\\?\\s`, "g");
/** Anything that already costs vertical space while it waits. */
const RESERVED = /Skeleton|animate-pulse|animate-spin|Loader/;
/**
 * A structure whose height grows with the number of records.
 *
 * `Table` is named next to the lower-case tag on purpose: rendering the same
 * table through `ui/Table` removes the word `table` from the loaded arm and
 * leaves the shift untouched, so an adoption would otherwise read as a resolved
 * placeholder and lower the baseline on its own.
 */
const REPEATED = /\.map\(|<(?:ul|ol|table|tbody)[\s/>]|<Table[\s/>]/;
/**
 * The whole arm is one call — the height lives inside that function.
 *
 * `t()` is excluded by name: a translation call is a text node, which is the
 * exact shape this rule is about, and reading it as an opaque renderer would
 * exempt the most common violation.
 */
const HELPER_CALL = /^\s*\(?\s*(?!t[_0-9]*\s*\()[A-Za-z_$][\w$.]*\s*\([\s\S]*\)\s*\)?\s*$/;

/**
 * The two arms of the ternary whose `?` sits at `from`.
 *
 * An arm is JSX, so a depth count over brackets alone is not enough: a class
 * list holds `max-h-[min(60vh,420px)]`, whose parens are not calls, and an
 * element closes with a tag rather than a bracket. Quote state, template state
 * and a JSX element stack are therefore all tracked, and `:` only ends the first
 * arm when every one of them is at zero — which is also what keeps a nested
 * `a ? b : c` inside an attribute expression from being read as the split.
 *
 * Returns null when no top-level `:` is reachable, meaning the `?` was not a
 * ternary (an optional chain, a `?:` inside a string) and nothing is reported.
 */
function branches(src, from) {
  const scan = (start, stopAtColon) => {
    let round = 0;
    let square = 0;
    let curly = 0;
    let jsx = 0;
    let quote = null;
    let inTemplate = false;
    const templateStack = [];
    let out = "";
    for (let i = start; i < src.length; i += 1) {
      const c = src[i];
      if (quote) {
        if (c === "\\") i += 1;
        else if (c === quote) quote = null;
        continue;
      }
      if (inTemplate) {
        if (c === "\\") i += 1;
        else if (c === "`") inTemplate = templateStack.pop() ?? false;
        else if (c === "$" && src[i + 1] === "{") {
          templateStack.push(true);
          inTemplate = false;
          i += 1;
        }
        continue;
      }
      if (c === "'" || c === '"') {
        quote = c;
        continue;
      }
      if (c === "`") {
        inTemplate = true;
        continue;
      }
      if (c === "<") {
        if (src.startsWith("</", i)) {
          const gt = src.indexOf(">", i);
          if (gt === -1) return null;
          if (jsx > 0) jsx -= 1;
          out += src.slice(i, gt + 1);
          i = gt;
          continue;
        }
        if (src.startsWith("<>", i)) {
          jsx += 1;
          i += 1;
          out += "<>";
          continue;
        }
        if (/[A-Za-z]/.test(src[i + 1] || "")) {
          const end = findTagEnd(src, i);
          if (end === -1) return null;
          if (src[end - 2] !== "/") jsx += 1;
          // The tag text belongs to the arm: whether the arm reserves height is
          // written in the element it renders, so dropping it here would make
          // `<SkeletonRows />` look like an empty branch.
          out += src.slice(i, end);
          i = end - 1;
          continue;
        }
        continue;
      }
      if (c === "(") round += 1;
      else if (c === ")") {
        if (round === 0) break;
        round -= 1;
      } else if (c === "[") square += 1;
      else if (c === "]") square -= 1;
      else if (c === "{") curly += 1;
      else if (c === "}") {
        if (curly === 0) break;
        curly -= 1;
      } else if (
        stopAtColon &&
        c === ":" &&
        round === 0 &&
        curly === 0 &&
        square === 0 &&
        jsx === 0
      ) {
        return { text: out, colon: i };
      }
      out += c;
    }
    return { text: out, colon: -1 };
  };

  const first = scan(from, true);
  if (first.colon === -1) return null;
  const second = scan(first.colon + 1, false);
  return { cons: first.text, alt: second.text };
}

/**
 * Placeholders in one comment-stripped source that swap a text line for a list.
 *
 * Pure, so the test can hand it invented sources: a guard whose only proof is
 * the repository it scans cannot tell a rule from an accident of what is
 * currently committed.
 */
export function scanLoadingPlaceholders(rel, src) {
  const findings = [];
  TERNARY.lastIndex = 0;
  let m;
  while ((m = TERNARY.exec(src)) !== null) {
    // `loading ?? <List />` ends with `? ` too and would match; a coalescing
    // operator has a second `?` where the ternary's single `?` sits.
    const q = m.index + m[0].lastIndexOf("?");
    if (src[q - 1] === "?") continue;
    // `t("admin:loading")` puts the word `loading` inside a key, and the next
    // real `?` can be within the gap the pattern allows — which would read the
    // arm's own text as a second condition. A flag is an identifier, so a `:`
    // or a quote directly before it means the match landed in a string.
    const before = src[m.index - 1];
    if (before === ":" || before === '"' || before === "'" || before === "`") continue;
    // `visible.length === 0 && !loading ? <li>nothing yet</li> : rows.map(…)` is
    // an empty state, not a loading state: negating the flag flips which arm is
    // which, and a placeholder painted into the empty branch would reserve space
    // for records that are never coming.
    let bang = m.index - 1;
    while (bang >= 0 && /\s/.test(src[bang])) bang -= 1;
    if (src[bang] === "!") continue;
    const parts = branches(src, q + 1);
    if (!parts) continue;
    const { cons, alt } = parts;
    if (cons.length < 4 || cons.length > 4000) continue;
    if (RESERVED.test(cons)) continue;
    // An arm that is only a call hands the height to that function; the guard
    // cannot read through it and must not guess that a helper renders a text
    // line. `src/ui/Table.tsx` and `AdminUsers` reserve inside such helpers.
    if (!cons.includes("<") && HELPER_CALL.test(cons)) continue;
    if (!REPEATED.test(alt)) continue;
    findings.push({
      line: src.slice(0, m.index).split("\n").length,
      flag: m[1],
      text: cons.replace(/\s+/g, " ").trim().slice(0, 90),
      into: alt.replace(/\s+/g, " ").trim().slice(0, 70),
    });
  }
  return findings;
}

/**
 * Which files grew past their recorded count, and which records are stale?
 *
 * Split out from the filesystem walk for the same reason as the scanner: the
 * ratchet direction — up fails, down only warns — is the whole guard, and it
 * must be testable without touching the ledger the pre-commit hook reads.
 */
export function diffBaseline(baseline, scanned) {
  const grew = [];
  const stale = [];
  for (const [rel, n] of scanned) {
    const allowed = baseline[rel] ?? 0;
    if (n > allowed) grew.push({ rel, n, allowed });
  }
  for (const [rel, recorded] of Object.entries(baseline)) {
    const now = scanned.get(rel) ?? 0;
    if (now < recorded) stale.push({ rel, was: recorded, now });
  }
  return { grew, stale };
}

async function readBaseline() {
  try {
    return JSON.parse(await readFile(BASELINE, "utf8"));
  } catch {
    return {};
  }
}

export async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function checkLoadingPlaceholder() {
  const baseline = await readBaseline();
  const scanned = new Map();
  const findings = [];
  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file).split("\\").join("/");
    const src = stripComments(await readFile(file, "utf8"));
    const found = scanLoadingPlaceholders(rel, src);
    if (found.length) {
      scanned.set(rel, found.length);
      for (const f of found) findings.push({ rel, ...f });
    }
  }
  const { grew, stale } = diffBaseline(baseline, scanned);
  let total = 0;
  for (const n of scanned.values()) total += n;
  return { grew, stale, findings, total, files: scanned };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  checkLoadingPlaceholder()
    .then(async (result) => {
      if (process.argv.includes("--update")) {
        const out = {};
        for (const [rel, n] of [...result.files].sort()) out[rel] = n;
        await writeFile(BASELINE, `${JSON.stringify(out, null, 2)}\n`, "utf8");
        console.log(
          `[loading-placeholder] baseline geschrieben: ${Object.keys(out).length} Datei(en), ${result.total} Stelle(n)`
        );
        return;
      }
      if (process.argv.includes("--explain")) {
        for (const f of result.findings) {
          console.log(`${f.rel}:${f.line} (${f.flag}) "${f.text}" -> ${f.into}`);
        }
        console.log(`[loading-placeholder] ${result.total} Stelle(n) in ${result.files.size} Datei(en)`);
        return;
      }
      if (result.stale.length) {
        console.error(
          `[loading-placeholder] veraltete Baseline-Einträge (run --update): ${result.stale.length}`
        );
        for (const s of result.stale) console.error(`  ${s.rel} war ${s.was}, jetzt ${s.now}`);
      }
      if (result.grew.length) {
        console.error(
          `[loading-placeholder] FAILED - ${result.grew.length} Datei(en) über der aufgezeichneten Zahl:`
        );
        for (const g of result.grew) {
          console.error(`  ${g.rel} ${g.n} statt max ${g.allowed}`);
        }
        console.error(
          "[loading-placeholder] ein Ladezweig, der gegen eine Liste tauscht, muss die Höhe der Liste reservieren (ui/Skeleton), sonst wandert alles unter ihm."
        );
        process.exit(1);
      }
      console.log(
        `[loading-placeholder] OK - ${result.total} Ladezweig(e) tauschen Text gegen eine Liste, alle auf oder unter der aufgezeichneten Zahl.`
      );
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}