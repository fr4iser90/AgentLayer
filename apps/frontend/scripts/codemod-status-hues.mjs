#!/usr/bin/env node
/**
 * Status-hue codemod (Welle 4, block A5).
 *
 * Four hues had become spelling variants of four tokens: red/danger,
 * amber/warning, emerald/success, sky/accent. Unlike the polysemous
 * orange/indigo/rose pass (codemod-semantic-hues.mjs, which maps per site),
 * this one maps per rule, because here the hue DOES mean the status — that is
 * what made it worth automating and also what makes it dangerous: a rule that
 * drops a lightness level silently can move a label from 7:1 to 4.3:1.
 *
 * The level is what carries the contrast, the hue carries the meaning, and the
 * tokens carry one level each. So the mapping is chosen by what the class has to
 * sit on:
 *
 *   bg-<hue>-950/x, bg-<hue>-{4..8}00/x<=40   -> bg-<t>-subtle
 *        a tint a light label sits on. `subtle` is the palette's own 15-16 %
 *        tint of DEFAULT; the source alpha is dropped on purpose — keeping it
 *        would keep a fifth tint value per hue, which is the drift.
 *   bg-<hue>-{5..8}00/x>40, solid            -> bg-<t>  (+ hover -> <t>-hover)
 *        a solid fill. Those sites already carry `text-ink-on-fill`, verified
 *        before this rule was written, so the dark ink does not move with it.
 *   text-<hue>-{100..300}                     -> text-badge-<t>
 *   text-<hue>-{400..900}                     -> text-<t>
 *        100-300 is a label, 400+ is the status colour itself. A badge tone is
 *        6.5-8.4:1 on card AND on its own subtle chip, so the label rule is
 *        safe without knowing what it sits on — which matters, because half of
 *        them are built in an array where the fill is a different string.
 *   border/ring/divide/outline-<hue>-n(/a)    -> same property, same alpha
 *
 * Post-pass, per string literal: `bg-<t>-subtle` (or an alpha tint) together
 * with `text-<t>` becomes `text-badge-<t>`, and `bg-<t>` solid together with
 * `text-<t>` becomes `text-ink-on-fill`. That is the pair the tokens exist to
 * make untypable, and it is the one the level rules above cannot see on their
 * own. A literal with a solid fill and a status label is reported rather than
 * rewritten when the label is already something else — the codemod does not
 * invent a decision.
 *
 * Skipped files are the catalogues: a colour that indexes a set of peer kinds
 * (activity kinds, run-card kinds, model capabilities) is not a status, and
 * collapsing it would delete the distinction the surface draws. They are listed
 * in the guards' INTENTIONAL maps with that reason.
 *
 * Run: node scripts/codemod-status-hues.mjs [--dry] [--hue=sky] [--explain]
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const HUES = { red: "danger", amber: "warning", emerald: "success", sky: "accent" };

// Catalogue keys — see the header. Not a file skip: a file that indexes a
// catalogue also carries ordinary chrome, and skipping the whole file left its
// links, icons and `<pre>` borders in `sky`/`emerald` while the file read as
// reviewed. Only the classes that ARE catalogue keys survive, listed by exact
// spelling; everything else in those files maps by rule. A listed class that is
// no longer in the tree fails the run (see `stale` in main) so the list cannot
// outlive the decision.
const PRESERVE = {
  "features/chat/AgentActivityPanel.tsx": [
    "border-sky-500/45",
    "border-sky-500/50",
    "border-emerald-500/50",
    "border-emerald-600/40",
    "border-amber-500/45",
    "border-amber-500/50",
  ],
  "features/chat/RunCardBlock.tsx": [
    "border-sky-500/35",
    "border-amber-500/45",
    "bg-sky-950/15",
    "bg-amber-950/20",
  ],
  "features/chat/ModelCatalogSelect.tsx": [
    "border-sky-400/30",
    "bg-sky-500/10",
    "text-sky-100",
    "border-amber-400/35",
    "bg-amber-500/15",
    "text-amber-100",
    "border-emerald-400/35",
    "bg-emerald-500/15",
    "text-emerald-100",
  ],
};

const SCAN_EXT = [".tsx", ".jsx", ".ts"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const HUE_ALT = Object.keys(HUES).join("|");
const PROPS = "bg|text|border|ring|divide|outline|placeholder|decoration|shadow|accent|caret|fill|stroke";

// A class with its variant chain. The leading boundary is the same one both
// colour guards converged on after missing a variant-prefixed class each.
const CLASS_RE = new RegExp(
  `(^|[^A-Za-z0-9-])((?:[a-zA-Z0-9-]+:)*(?:${PROPS}|from|to|via)-(?:${HUE_ALT})-[0-9]{2,4}(?:/[0-9]{1,3})?)(?![a-z0-9-])`,
  "g"
);

function levelOf(cls) {
  const m = /-(\d{2,4})(?:\/(\d{1,3}))?$/.exec(cls);
  return { level: Number(m[1]), alpha: m[2] === undefined ? null : Number(m[2]) };
}

/**
 * The one mapping decision for one class. Returns the replacement class, or
 * null to leave it alone (with a reason collected for --explain).
 */
export function mapClass(cls, notes) {
  const colon = cls.lastIndexOf(":");
  const variants = colon === -1 ? "" : cls.slice(0, colon + 1);
  const bare = cls.slice(colon + 1);
  // A class this codemod has already produced, or one of the hues it does not
  // own, has no `-<hue>-<level>` in it. Returning null rather than reading the
  // level off a failed match: the caller pre-filters today, but an exported
  // rule that crashes on the input it is *documented* to leave alone makes the
  // next caller — a test, or a re-run over partly migrated code — pay for it.
  const hueMatch = new RegExp(`-(${HUE_ALT})-\\d`).exec(bare);
  if (!hueMatch) return null;
  const prop = /^([a-z-]+?)-[a-z]+-\d/.exec(bare)?.[1] ?? bare.split("-")[0];
  const token = HUES[hueMatch[1]];
  const { level, alpha } = levelOf(bare);
  const isHover = /(^|:)hover:/.test(variants) || /(^|:)focus:/.test(variants) || /(^|:)active:/.test(variants);

  if (prop === "bg") {
    if (alpha !== null && alpha <= 40) return `${variants}bg-${token}-subtle`;
    if (level >= 900 || level <= 100) return `${variants}bg-${token}-subtle`;
    // Solid fill: the interactive variant of a token is its hover tone, and the
    // plain DEFAULT stands in for a pressed/active paint, which has no separate
    // value in the palette.
    if (isHover) return `${variants}bg-${token}-hover`;
    return `${variants}bg-${token}`;
  }

  if (prop === "text") {
    if (level <= 300) return `${variants}text-badge-${token}`;
    if (isHover) return `${variants}text-${token}-hover`;
    return `${variants}text-${token}`;
  }

  // Hairlines, rings, dividers: keep the alpha, swap the hue. A hairline at /30
  // over a tint is a deliberate softness; flattening it to full DEFAULT would
  // turn a separator into an outline.
  if (["border", "ring", "divide", "outline", "placeholder", "decoration", "shadow", "accent", "caret", "fill", "stroke"].includes(prop))
    return `${variants}${prop}-${token}${alpha !== null ? `/${alpha}` : ""}`;

  // Gradient stops (2 sites): keep the stop, swap the hue.
  notes.push(`${cls}: Gradient-Stopp`);
  return `${variants}${prop}-${token}${alpha !== null ? `/${alpha}` : ""}`;
}

/**
 * Second pass over one string literal: a status label on a same-literal status
 * fill. `text-danger` on `bg-danger-subtle` is 4.3:1 and looks intentional
 * forever, because both halves are correct tokens.
 */
export function fixLabelOnFill(literal) {
  let out = literal;
  for (const token of Object.values(HUES)) {
    // The boundary has to admit the quote that opens the literal, exactly like
    // the class regexes in both colour guards: without it, a fill in the FIRST
    // position of a className sees `"` where it expects whitespace, and the
    // pair goes unfixed while the run reports the file as clean.
    const hasTint = new RegExp(`(?:^|[\\s:"'\`])bg-${token}(?:-subtle|/\\d+)`).test(out);
    const hasSolid = new RegExp(`(?:^|[\\s:"'\`])bg-${token}(?![\\w/-])`).test(out);
    const label = new RegExp(`((?:[a-zA-Z0-9-]+:)*)text-${token}(?![-\\w])`, "g");
    if (hasTint) out = out.replace(label, `$1text-badge-${token}`);
    else if (hasSolid) out = out.replace(label, "$1text-ink-on-fill");
  }
  return out;
}

const LITERAL_RE = /"([^"\n]*)"|'([^'\n]*)'|`([^`\n]*)`/g;

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

async function main() {
  const dry = process.argv.includes("--dry");
  const explain = process.argv.includes("--explain");
  const only = /--hue=(\w+)/.exec(process.argv.join(" "))?.[1];
  const hueFilter = only ? { [only]: HUES[only] } : HUES;

  const counts = new Map();
  const notes = [];
  const hit = new Set();
  const written = [];
  let files = 0;
  let literalsFixed = 0;

  for await (const path of walk(SRC)) {
    const rel = path.slice(ROOT.length + 1).replace(/^src\//, "");
    const keep = new Set((PRESERVE[rel] ?? []).map((cls) => `${rel}::${cls}`));
    const before = await readFile(path, "utf8");

    const mapped = before.replace(CLASS_RE, (whole, lead, cls) => {
      const bare = cls.slice(cls.lastIndexOf(":") + 1);
      const key = `${rel}::${bare}`;
      if (keep.has(key)) {
        hit.add(key);
        return whole;
      }
      const hue = new RegExp(`-(${Object.keys(hueFilter).join("|")})-\\d`).exec(cls);
      if (!hue) return whole; // a hue not in this run
      const next = mapClass(cls, notes);
      if (!next || next === cls) return whole;
      counts.set(`${cls}  ->  ${next}`, (counts.get(`${cls}  ->  ${next}`) ?? 0) + 1);
      return lead + next;
    });

    let after = mapped;
    if (!explain) {
      after = mapped.replace(LITERAL_RE, (m) => {
        const fixed = fixLabelOnFill(m);
        if (fixed !== m) literalsFixed += 1;
        return fixed;
      });
    }

    if (after !== before) {
      files += 1;
      written.push({ path, after });
    }
  }

  // A preserved class that is no longer in the tree means the catalogue it
  // belongs to changed shape, or someone migrated it and forgot the list. Either
  // way the next reader would take "catalogue key" as a reason for something
  // that does not exist, so the run says so instead of reporting a clean map.
  const listed = Object.entries(PRESERVE).flatMap(([f, list]) => list.map((c) => `${f}::${c}`));
  const stale = listed.filter((k) => !hit.has(k));
  if (stale.length) {
    console.error(`[status-hues] Abbruch — ${stale.length} konservierte Klasse(n) treffen nichts mehr:`);
    for (const k of stale) console.error(`  ${k}`);
    console.error("[status-hues] Nichts geschrieben. Streiche die Klasse aus PRESERVE, oder stelle sie her.");
    process.exit(1);
  }

  const total = [...counts.values()].reduce((a, n) => a + n, 0);
  if (explain) {
    console.log(`[status-hues] ${total} Klasse(n) würden sich ändern in ${counts.size} Mustern, ${hit.size} Katalog-Schlüssel bleiben:`);
    for (const [pattern, n] of [...counts.entries()].sort((a, b) => b[1] - a[1]))
      console.log(`  ${String(n).padStart(4)}  ${pattern}`);
    for (const n of notes) console.log(`  ! ${n}`);
    return;
  }

  for (const { path, after } of written) {
    if (!dry) await writeFile(path, after, "utf8");
  }

  console.log(
    `[status-hues] ${total} Klasse(n) in ${files} Datei(en) gemappt, ${hit.size} Katalog-Schlüssel erhalten, ${literalsFixed} Literal(e) mit Label-auf-Fill-Paar korrigiert${dry ? " (dry-run, nichts geschrieben)" : ""}.`
  );
}

// The rule functions above are exported for tests, and a module that rewrites
// the tree when something imports it is a landmine: this file was first run by
// a test harness importing `mapClass`, which mapped 1015 classes as a side
// effect of looking at them. Main only runs when the file is the entry point.
const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}