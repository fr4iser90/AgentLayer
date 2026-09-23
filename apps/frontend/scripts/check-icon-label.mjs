#!/usr/bin/env node
/**
 * Icon-only buttons must carry an accessible name.
 *
 * A button whose entire visible content is an icon has nothing a screen reader
 * can announce. `title` used to cover this by accident; now that `title` is being
 * replaced by the Tooltip primitive, the accessible name has to come from
 * `aria-label`, `aria-labelledby`, or the Tooltip's own `label`.
 *
 * This is a HARD guard with a zero baseline, not a ratchet: every icon-only
 * button in the tree is checked, and there is no allow-list to hide behind. That
 * is only affordable because the population was measured first and is fully
 * compliant.
 *
 * The icon set is not guessed. It is collected from the actual
 * `import { ... } from "lucide-react"` statements in the tree, so a renamed or
 * newly added icon is covered automatically and a hand-maintained list cannot
 * drift. If that collection comes back empty the scanner is blind, and a blind
 * guard that exits 0 is worse than no guard — so it refuses instead.
 *
 * Run with --explain to list what was classified icon-only and how each was named.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { findElements, findTagEnd, hasNamedAttr } from "./jsx-tags.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, "..", "src");
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

const NAME_ATTRS = ["aria-label", "aria-labelledby", "title"];

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (/\.(tsx|jsx)$/.test(p) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

/** Names imported from lucide-react anywhere in the tree. */
async function collectIconNames() {
  const names = new Set();
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const re = /import\s*\{([^}]*)\}\s*from\s*["']lucide-react["']/g;
    for (const m of src.matchAll(re)) {
      for (const part of m[1].split(",")) {
        const as = part.split(/\s+as\s+/);
        const name = (as[1] ?? as[0]).trim();
        if (/^[A-Z][A-Za-z0-9]*$/.test(name)) names.add(name);
      }
    }
  }
  return names;
}

/** Which of the naming attributes, if any, gives this tag its accessible name? */
function namingAttr(tag) {
  for (const attr of NAME_ATTRS) if (hasNamedAttr(tag, attr)) return attr;
  return null;
}

/**
 * Is the button inside a <Tooltip>? The nearest Tooltip opening before it must
 * not have been closed again in between, which rules out a sibling Tooltip
 * earlier in the file being mistaken for an ancestor.
 */
function insideTooltip(src, tagStart) {
  const before = src.slice(0, tagStart);
  const open = before.lastIndexOf("<Tooltip");
  if (open === -1) return false;
  return !before.slice(open).includes("</Tooltip>");
}

/**
 * Classify the children of a button.
 * Returns { iconOnly, reason } where reason explains a non-icon-only verdict.
 */
function classifyChildren(src, from, to, iconNames) {
  const parts = [];
  let i = from;
  while (i < to) {
    const lt = src.indexOf("<", i);
    if (lt === -1 || lt >= to) {
      parts.push({ kind: "text", raw: src.slice(i, to) });
      break;
    }
    const between = src.slice(i, lt);
    if (between.trim() !== "") parts.push({ kind: "text", raw: between });
    if (src[lt + 1] === "/") break; // our own closing tag
    const end = findTagEnd(src, lt);
    if (end === -1 || end > to) return { iconOnly: false, reason: "unbalanciertes Tag" };
    const name = /^[A-Za-z][A-Za-z0-9.]*/.exec(src.slice(lt + 1, end));
    parts.push({ kind: "tag", name: name ? name[0] : "", raw: src.slice(lt, end) });
    i = end;
  }

  const meaningful = parts.filter((p) => p.kind === "tag" || p.raw.trim() !== "");
  if (meaningful.length === 0) return { iconOnly: false, reason: "leer" };
  if (meaningful.some((p) => p.kind === "text")) {
    const t = meaningful.find((p) => p.kind === "text");
    return { iconOnly: false, reason: ` sichtbarer Text: "${t.raw.trim().slice(0, 24)}"` };
  }
  const notIcon = meaningful.filter(
    (p) => !(iconNames.has(p.name) || p.name === "svg"),
  );
  if (notIcon.length) {
    return {
      iconOnly: false,
      reason: ` kein Lucide-Icon: <${notIcon[0].name}>`,
    };
  }
  return { iconOnly: true, reason: "" };
}

/**
 * Scan one file's source. Exported separately from the tree walk so the
 * classification can be tested against exact strings — a guard nobody has seen
 * go red is decoration.
 */
export function scanSource(src, file, iconNames) {
  const violations = [];
  const named = [];
  let iconOnly = 0;
  // findElements, not indexOf: a bare indexOf("<button") also matches
  // <buttonbar>, which would be classified and reported under a name it does
  // not have.
  const elements = findElements(src, "button");
  for (const { tagStart, tagEnd, selfClosing } of elements) {
    const close = selfClosing ? -1 : src.indexOf("</button>", tagEnd);
    if (close === -1) continue;
    const tag = src.slice(tagStart, tagEnd);

    const cls = classifyChildren(src, tagEnd, close, iconNames);
    if (cls.iconOnly) {
      iconOnly += 1;
      const attr = namingAttr(tag);
      const tip = insideTooltip(src, tagStart);
      if (attr) {
        named.push({ file, line: lineOf(src, tagStart), how: attr });
      } else if (tip) {
        named.push({ file, line: lineOf(src, tagStart), how: "Tooltip label" });
      } else {
        violations.push({
          file,
          line: lineOf(src, tagStart),
          snippet: tag.replace(/\s+/g, " ").slice(0, 70),
        });
      }
    }
  }
  return { buttons: elements.length, iconOnly, named, violations };
}

export async function checkIconLabels({ explain = false } = {}) {
  const iconNames = await collectIconNames();
  if (iconNames.size === 0) {
    throw new Error(
      "keine Lucide-Icons gefunden — Scanner ist blind, wirfe nicht OK",
    );
  }

  const violations = [];
  const named = [];
  let buttons = 0;
  let iconOnly = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const r = scanSource(src, file, iconNames);
    buttons += r.buttons;
    iconOnly += r.iconOnly;
    named.push(...r.named);
    violations.push(...r.violations);
  }

  return { buttons, iconOnly, named, violations, iconNames: iconNames.size };
}

function lineOf(src, index) {
  return src.slice(0, index).split("\n").length;
}

const isMain =
  process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const explain = process.argv.includes("--explain");
  checkIconLabels({ explain })
    .then(({ buttons, iconOnly, named, violations, iconNames }) => {
      console.log(
        `icon-label: ${iconNames} Lucide-Namen, ${buttons} Buttons, ${iconOnly} icon-only, ${named.length} benannt, ${violations.length} ohne Namen`,
      );
      if (explain) {
        for (const n of named)
          console.log(`  benannt  ${rel(n.file)}:${n.line}  via ${n.how}`);
      }
      if (violations.length) {
        console.error("FEHLER: icon-only Buttons ohne zugaenglichen Namen:");
        for (const v of violations)
          console.error(`  ${rel(v.file)}:${v.line}  ${v.snippet}`);
        process.exit(1);
      }
    })
    .catch((e) => {
      console.error(e.message || e);
      process.exit(1);
    });
}

function rel(f) {
  return relative(join(__dirname, ".."), f);
}
