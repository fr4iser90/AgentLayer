#!/usr/bin/env node
/**
 * Control-primitive guard.
 *
 * Two promises live in `Button.tsx` and `Field.tsx`: one place decides what a
 * control looks like, and one place decides what it costs to be focusable,
 * disabled, or on the ink-on-fill hue. Both are only true while the app writes
 * `<Button>` and `<TextInput>`. A 370th hand-painted `<button>` is not a style
 * nit — it is a control that missed the focus ring, the disabled hue, and the
 * touch-target height, and nothing in the build says so.
 *
 * Converting 370 call sites in one commit is how a refactor turns into a visual
 * regression hunt, so the rule is a ratchet: `control-baseline.json` records how
 * many bare `<button>` / `<input>` each file still has, and a file may only go
 * down. New file, new control, or a count that grows — failed. `--update` writes
 * the current counts after a conversion pass so the floor drops with the work.
 *
 * The second rule has no baseline. `variant="plain"` exists for exactly one
 * situation — a control that is the surface itself, where the primitive must
 * give up its fill, hairline and radius. Without `block` that control keeps its
 * inline box and its own padding while the caller adds layout classes on top,
 * which is the drift the variant was introduced to remove. Plain without block
 * is therefore always wrong, and no recorded exception makes it right.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { attrNames, findElements } from "./jsx-tags.mjs";
import { stripComments } from "./strip-comments.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "control-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/, /\.stories\./];
/** The primitives themselves define the bare tags — that is their job. */
const EXEMPT_DIR = "src/ui/";
/** Types and other non-rendering modules cannot hold JSX. */
const BARE = ["button", "input"];

/**
 * Bare controls and plain-without-block in one file.
 *
 * `src` must already have its comments stripped: JSX inside a doc comment is
 * not a call site, and matching on raw text would make a comment in `Button.tsx`
 * that shows `<button>` an offence against its own rule.
 */
export function scanControls(rel, src) {
  const findings = [];
  if (!rel.startsWith("src/") || rel.startsWith(EXEMPT_DIR)) {
    return { counts: {}, findings };
  }
  const counts = {};
  for (const tag of BARE) {
    const found = findElements(src, tag);
    if (found.length) counts[tag] = found.length;
    for (const el of found) {
      const line = src.slice(0, el.tagStart).split("\n").length;
      findings.push({
        kind: `bare-${tag}`,
        line,
        text: src.slice(el.tagStart, Math.min(el.tagEnd, el.tagStart + 60)).replace(/\s+/g, " "),
      });
    }
  }
  for (const el of findElements(src, "Button")) {
    const tag = src.slice(el.tagStart, el.tagEnd);
    const plain = /(^|[\s{])variant=(?:"plain"|\{["`]plain["`]\})/.test(tag);
    if (plain && !attrNames(tag).includes("block")) {
      findings.push({
        kind: "plain-without-block",
        line: src.slice(0, el.tagStart).split("\n").length,
        text: tag.replace(/\s+/g, " ").slice(0, 60),
      });
    }
  }
  return { counts, findings };
}

/**
 * Which recorded counts are still exceeded, and which entries have gone stale?
 *
 * Pure so the test can hand it an invented baseline instead of rewriting the
 * recorded one — a guard whose test mutates its own ledger proves nothing about
 * the ledger the pre-commit hook reads.
 */
export function diffBaseline(baseline, scanned) {
  const grew = [];
  const stale = [];
  for (const [rel, counts] of scanned) {
    const recorded = baseline[rel] ?? {};
    for (const [tag, n] of Object.entries(counts)) {
      const allowed = recorded[tag] ?? 0;
      if (n > allowed) grew.push({ rel, tag, n, allowed });
    }
  }
  for (const [rel, recorded] of Object.entries(baseline)) {
    const now = scanned.get(rel) ?? {};
    for (const tag of Object.keys(recorded)) {
      if ((now[tag] ?? 0) < recorded[tag]) stale.push({ rel, tag, was: recorded[tag], now: now[tag] ?? 0 });
    }
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

export async function checkControlPrimitive() {
  const baseline = await readBaseline();
  const scanned = new Map();
  const plain = [];
  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file).split("\\").join("/");
    const { counts, findings } = scanControls(rel, stripComments(await readFile(file, "utf8")));
    if (Object.keys(counts).length) scanned.set(rel, counts);
    for (const f of findings.filter((x) => x.kind === "plain-without-block")) {
      plain.push({ rel, ...f });
    }
  }
  const { grew, stale } = diffBaseline(baseline, scanned);
  const totals = {};
  for (const counts of scanned.values()) {
    for (const [tag, n] of Object.entries(counts)) totals[tag] = (totals[tag] ?? 0) + n;
  }
  return { grew, stale, plain, totals, baseline, files: scanned };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  checkControlPrimitive()
    .then(async (result) => {
      if (process.argv.includes("--update")) {
        const out = {};
        for (const [rel, counts] of [...result.files].sort()) out[rel] = counts;
        await writeFile(BASELINE, `${JSON.stringify(out, null, 2)}\n`, "utf8");
        console.log(
          `[control-primitive] baseline geschrieben: ${Object.keys(out).length} Datei(en), button=${result.totals.button ?? 0} input=${result.totals.input ?? 0}`
        );
        return;
      }
      const ok = result.grew.length === 0 && result.plain.length === 0;
      if (result.grew.length) {
        console.error(
          `[control-primitive] FAILED - ${result.grew.length} Datei(en) über der aufgezeichneten Zahl nackter Controls:`
        );
        for (const g of result.grew) {
          console.error(`  ${g.rel} <${g.tag}> ${g.n} statt max ${g.allowed}`);
        }
      }
      if (result.plain.length) {
        console.error(
          `[control-primitive] FAILED - ${result.plain.length} Button mit variant="plain" ohne block:`
        );
        for (const p of result.plain) console.error(`  ${p.rel}:${p.line} ${p.text}`);
        console.error(
          '[control-primitive] plain ist für Flächen, die die Kontrolle selbst sind — ohne block behält sie ihre Inline-Box und ihr Padding und der Caller legt Layout darüber.'
        );
      }
      if (result.stale.length) {
        console.error(
          `[control-primitive] veraltete Baseline-Einträge (run --update): ${result.stale.length}`
        );
        for (const s of result.stale) console.error(`  ${s.rel} <${s.tag}> war ${s.was}, jetzt ${s.now}`);
      }
      if (!ok) process.exit(1);
      console.log(
        `[control-primitive] OK - button=${result.totals.button ?? 0} input=${result.totals.input ?? 0} nackte Controls ausserhalb src/ui/, alle auf oder unter der aufgezeichneten Zahl; ${result.plain.length} plain ohne block.`
      );
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}