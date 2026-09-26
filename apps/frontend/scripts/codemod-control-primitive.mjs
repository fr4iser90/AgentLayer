#!/usr/bin/env node
/**
 * Control-primitive codemod.
 *
 * Moves hand-drawn `<input>` / `<select>` / `<textarea>` / `<button>` onto
 * `ui/Field` and `ui/Button`. The reason this is a script and not an editor
 * pass is the count: 357 buttons and 293 fields spread over 140 files, where a
 * hand pass produces "most of them, unevenly" — the exact state the primitives
 * exist to end.
 *
 * It is deliberately conservative, because a codemod that guesses is worse than
 * no codemod: an ugly control is fixable, a silently changed handler is not.
 *
 *   - Only a `className` given as a string literal is touched. `className={...}`
 *     means the classes are conditional on state, and dropping them into
 *     `className="…"` would drop the condition — those sites are reported and
 *     left alone.
 *   - Attributes are never reordered, renamed or removed — only the class string
 *     and the tag name change. Handlers, `value`, `name`, `id`, `aria-*` all stay
 *     where they were.
 *   - `checkbox` / `radio` / `file` / `range` / `color` / `hidden` inputs are
 *     skipped: they are not text fields and `FIELD_BASE`'s height, padding and
 *     background would break them.
 *
 * Classes the primitive already provides are dropped rather than passed through.
 * Passing them would leave two utilities fighting for the same property, and in
 * Tailwind the winner is the order in the generated stylesheet, not the order in
 * the class attribute — the file that "still looks right" today would be right
 * by accident and wrong after the next unrelated class was added.
 *
 * Usage: node scripts/codemod-control-primitive.mjs [--elements=input,select] [--dry-run] [--report]
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { findElements } from "./jsx-tags.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const argv = process.argv.slice(2);
const DRY = argv.includes("--dry-run");
const REPORT = argv.includes("--report");
const elementsArg = (argv.find((a) => a.startsWith("--elements=")) || "").slice(
  "--elements=".length
);
const WANTED = (elementsArg || "input,select,textarea,button").split(",");

/** Controls that are not text fields and must keep their own box. */
const SKIP_INPUT_TYPES = new Set([
  "checkbox",
  "radio",
  "file",
  "range",
  "color",
  "hidden",
]);

const FIELD_TARGET = { input: "TextInput", select: "Select", textarea: "TextArea" };

/**
 * A `<button>` doing layout work instead of acting as a control.
 *
 * `Button` gives every instance one content box: `inline-flex … justify-center`
 * and a fixed height per size. A surface that spreads its label left, stacks an
 * icon over a caption, or grows with its content is not a control that happens
 * to be a button — it is a clickable card or an accordion header. The
 * primitive's utilities win the collision on `justify-*` and on height because
 * Tailwind resolves by stylesheet order, not by author intent, so converting
 * those sites buys a smaller count and 28 visibly collapsed panels.
 *
 * They stay as they are and are counted separately, so the number reported by
 * this script says what was migrated rather than what a regex could reach.
 */
const LAYOUT_BUTTON = [
  /^justify-(between|start|around|evenly)$/,
  /^flex-col$/,
  /^items-start$/,
  /^text-left$/,
  /^text-right$/,
  /^whitespace-normal$/,
  /^h-auto$/,
  /^min-h-\S+$/,
];

/**
 * `Field`'s FIELD_BASE and the per-control additions. Anything here is owned by
 * the primitive and must not survive in the caller's className.
 */
const FIELD_OWNED = [
  /^w-full$/,
  /^rounded-\S+$/,
  /^border$/,
  /^border-line\S*$/,
  /^bg-field$/,
  /^bg-black\/\d+$/,
  /^bg-white\/\d+$/,
  /^bg-transparent$/,
  /^px-\S+$/,
  /^py-\S+$/,
  /^p-\S+$/,
  /^h-\d+$/,
  /^text-body$/,
  /^text-sm$/,
  /^text-ink-primary$/,
  /^placeholder:text-\S+$/,
  /^transition-\S+$/,
  /^duration-\S+$/,
  /^ease-\S+$/,
  /^focus:\S+$/,
  /^disabled:\S+$/,
  /^read-only:\S+$/,
  /^font-mono$/,
];

/** `Button`'s BASE + variant surface + size box. */
const BUTTON_OWNED = [
  /^inline-flex$/,
  /^flex$/,
  /^items-center$/,
  /^justify-center$/,
  /^select-none$/,
  /^whitespace-nowrap$/,
  /^font-medium$/,
  /^rounded-\S+$/,
  /^transition-\S+$/,
  /^duration-\S+$/,
  /^ease-\S+$/,
  /^focus(-visible)?:\S+$/,
  /^disabled:\S+$/,
  /^active:bg-(accent|success|warning|danger)\S*$/,
  /^hover:bg-(accent|success|warning|danger)\S*$/,
  /^bg-(accent|success|warning|danger)(-\S+)?$/,
  /^bg-emerald-\d+$/,
  /^bg-red-\d+$/,
  /^bg-sky-\d+$/,
  /^bg-amber-\d+$/,
  /^text-(white|ink-on-fill|ink-primary)$/,
  /^border$/,
  /^border-line\S*$/,
  /^hover:border-\S+$/,
  /^gap-base$/,
];

/**
 * What `Button` still provides on a `block` + `variant="plain"` surface.
 *
 * `plain` is the base and nothing else, so only the base's own utilities may be
 * stripped. Everything the surface legitimately owns — its radius, background,
 * border, padding, height and axis alignment — has to survive in the class
 * string, because the primitive no longer supplies it.
 */
const BUTTON_PLAIN_OWNED = [
  /^inline-flex$/,
  /^flex$/,
  /^select-none$/,
  /^font-medium$/,
  /^transition-\S+$/,
  /^duration-\S+$/,
  /^ease-\S+$/,
  /^focus(-visible)?:\S+$/,
  /^disabled:\S+$/,
  /^text-left$/,
];

const FILL_TONE = [
  [/^bg-success$/, "success"],
  [/^bg-emerald-\d+$/, "success"],
  [/^bg-warning$/, "warning"],
  [/^bg-amber-\d+$/, "warning"],
  [/^bg-danger$/, "danger"],
  [/^bg-red-\d+$/, "danger"],
];

function classifyVariant(classes) {
  const has = (re) => classes.some((c) => re.test(c));
  const tone = FILL_TONE.map(([re, t]) => (has(re) ? t : null)).find(Boolean);
  if (tone) return { variant: "primary", tone };
  if (has(/^bg-accent/) || has(/^bg-sky-\d+$/)) return { variant: "primary" };
  if (has(/^border$/) || has(/^border-line/)) return { variant: "secondary" };
  if (has(/^bg-white\/\d+$/)) return { variant: "secondary" };
  return { variant: "ghost" };
}

function classifySize(classes) {
  const has = (re) => classes.some((c) => re.test(c));
  const square =
    has(/^(h|w)-(\d+)$/) &&
    (has(/^p-0$/) || has(/^p-1$/) || has(/^p-2$/) || has(/^p-\S+$/)) &&
    classes.filter((c) => /^(h|w)-\d+$/.test(c)).length >= 2;
  if (has(/^h-9$/) || has(/^h-10$/) || has(/^px-wide$/)) return { size: "lg", square };
  if (has(/^h-6$/) || has(/^h-7$/) || has(/^text-xs$/) || has(/^text-label$/))
    return { size: "sm", square };
  return { size: "md", square };
}

function stripOwned(classes, owned) {
  return classes.filter((c) => !owned.some((re) => re.test(c)));
}

function toPosix(p) {
  return p.split(sep).join("/");
}

function importPath(file, module) {
  const rel = relative(dirname(file), join(SRC, "ui", module))
    .split(sep)
    .join("/");
  return rel.startsWith(".") ? rel : `./${rel}`;
}

/** Insert (start, end, text) sorted so they can be applied back-to-front. */
function applyEdits(src, edits) {
  const sorted = [...edits].sort((a, b) => b.start - a.start);
  let out = src;
  for (const e of sorted) {
    out = out.slice(0, e.start) + e.text + out.slice(e.end);
  }
  return out;
}

/**
 * Adds the primitive import without cutting an existing one in half.
 *
 * The first version inserted after the last *line* starting with `import`,
 * which is the middle of a wrapped import — the syntax error landed in forty
 * files before anything else got reported. Imports are matched as statements
 * now: merge into an import from the same module when one exists, otherwise
 * insert after the end of the last import statement.
 */
function ensureImport(src, names, from, mod) {
  const sorted = [...names].sort();
  const stmt = `import { ${sorted.join(", ")} } from "${from}";`;
  const named = /^import\s*\{([\s\S]*?)\}\s*from\s*"([^"]+)";/gm;
  let m;
  while ((m = named.exec(src)) !== null) {
    // Only the module that actually exports these names — merging `TextArea`
    // into the file's existing `../ui/Button` import would not resolve.
    if (m[2] === from || m[2].endsWith(`/ui/${mod}`)) {
      const spec = m[2];
      // Everything already in the braces is kept, `type Foo` included — dropping
      // it would compile but silently remove a used type import.
      const existing = m[1]
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const merged = [...new Set([...existing, ...sorted])].sort();
      return (
        src.slice(0, m.index) +
        `import { ${merged.join(", ")} } from "${spec}";` +
        src.slice(m.index + m[0].length)
      );
    }
  }
  let lastEnd = -1;
  const statements = /^import\b[\s\S]*?(?:\bfrom\s*)?"[^"]+";/gm;
  while ((m = statements.exec(src)) !== null) lastEnd = m.index + m[0].length;
  if (lastEnd === -1) return `${stmt}\n${src}`;
  return src.slice(0, lastEnd) + `\n${stmt}` + src.slice(lastEnd);
}

/** True when `pos` sits inside a `<form>` in `src` — forms are never nested here. */
function insideForm(src, pos) {
  const before = src.slice(0, pos);
  return (
    (before.match(/<form\b/g) || []).length >
    (before.match(/<\/form>/g) || []).length
  );
}

function walk(dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const f = join(dir, e.name);
    if (e.isDirectory()) {
      if (!/node_modules|dist/.test(f)) out.push(...walk(f));
    } else if (
      /\.(tsx|jsx)$/.test(f) &&
      !/\.test\./.test(f) &&
      !toPosix(f).includes("/src/ui/")
    ) {
      out.push(f);
    }
  }
  return out;
}

const stats = {
  converted: 0,
  skippedExprClass: 0,
  skippedType: 0,
  block: 0,
  files: 0,
};
const skipDetail = [];

for (const file of walk(SRC)) {
  let src = readFileSync(file, "utf8");
  const original = src;
  const edits = [];
  const addNames = new Set();

  for (const tag of WANTED) {
    const isField = tag in FIELD_TARGET;
    const target = isField ? FIELD_TARGET[tag] : "Button";
    for (const el of findElements(src, tag)) {
      const open = src.slice(el.tagStart, el.tagEnd);
      const classMatch = open.match(/className="([^"]*)"/);
      if (!classMatch) {
        if (/className=\{/.test(open)) {
          stats.skippedExprClass += 1;
          skipDetail.push(`${toPosix(file)}: ${tag} className={…}`);
        }
        continue;
      }
      if (tag === "input") {
        const type = (open.match(/\btype="([^"]*)"/) || [])[1];
        if (type && SKIP_INPUT_TYPES.has(type)) {
          stats.skippedType += 1;
          continue;
        }
        // A dynamic `type` is a checkbox on one render and a text field on the
        // next; `role` means the element is not a plain field at all. Neither is
        // decidable from the source, so neither is touched.
        if (/\btype=\{|\brole=/.test(open)) {
          stats.skippedType += 1;
          continue;
        }
      }
      // `Select` requires children — an empty `<select />` would not typecheck.
      if (tag === "select" && el.selfClosing) {
        stats.skippedType += 1;
        continue;
      }

      const classes = classMatch[1].split(/\s+/).filter(Boolean);
      const block =
        tag === "button" &&
        classes.some((c) => LAYOUT_BUTTON.some((re) => re.test(c)));
      const owned = isField
        ? FIELD_OWNED
        : block
          ? BUTTON_PLAIN_OWNED
          : BUTTON_OWNED;
      const rest = stripOwned(classes, owned);

      const attrs = [];
      if (isField) {
        if (tag !== "select" && classes.includes("font-mono")) attrs.push("mono");
        // `bg-transparent` on a hand-drawn field meant "the panel behind me is
        // the surface" — that intent is the `bare` prop, not a leftover class.
        if (classes.includes("bg-transparent")) attrs.push("bare");
      } else if (block) {
        // A surface that paints itself keeps its paint; it gains the base, the
        // focus ring and `type="button"`, which is the part it was missing.
        attrs.push('variant="plain"', "block");
      } else {
        const { variant, tone } = classifyVariant(classes);
        const { size, square } = classifySize(classes);
        if (variant !== "secondary") attrs.push(`variant="${variant}"`);
        if (variant === "primary" && tone && tone !== "accent")
          attrs.push(`tone="${tone}"`);
        if (size !== "md") attrs.push(`size="${size}"`);
        if (square) attrs.push("square");
      }
      // `Button` defaults to `type="button"`. A bare `<button>` inside a form
      // submits, and quietly turning a submit into a no-op is the one behaviour
      // change this codemod must never make.
      if (tag === "button" && !/\btype=/.test(open) && insideForm(src, el.tagStart)) {
        attrs.push('type="submit"');
      }

      const classAttr = rest.length ? ` className="${rest.join(" ")}"` : "";
      // Keep the attribute order the author used: swap the className in place so
      // a review diff stays one line instead of becoming a reflowed tag.
      const indent = (src.slice(0, el.tagStart).match(/[ \t]*$/) || [""])[0];
      const head = open.includes("\n")
        ? `<${target}\n${indent}  ${attrs.join(`\n${indent}  `)}`
        : `<${target}${attrs.length ? ` ${attrs.join(" ")}` : ""}`;
      const newOpen = open
        .replace(new RegExp(`<${tag}\\b`), head)
        .replace(/className="[^"]*"/, classAttr.trimStart())
        .replace(/[ \t]+\n/g, "\n")
        .split("\n")
        // A className that sat on its own line leaves that line empty, and the
        // closing `>` loses the indentation it had relative to the tag.
        .filter((line) => line.trim() !== "")
        .map((line) => (/^\s*\/?>$/.test(line) ? indent + line.trim() : line))
        .join("\n");

      edits.push({ start: el.tagStart, end: el.tagEnd, text: newOpen });
      if (!el.selfClosing) {
        const close = src.indexOf(`</${tag}>`, el.tagEnd);
        if (close !== -1) {
          edits.push({
            start: close,
            end: close + tag.length + 3,
            text: `</${target}>`,
          });
        }
      }
      addNames.add(target);
      if (block) stats.block += 1;
      stats.converted += 1;
    }
  }

  if (!edits.length) continue;
  src = applyEdits(original, edits);
  // `src/ui` has no index file — callers import `../ui/Button` and `../ui/Field`
  // separately, so the names are grouped by the module that exports them.
  const byModule = new Map();
  for (const name of addNames) {
    const mod = name === "Button" ? "Button" : "Field";
    if (!byModule.has(mod)) byModule.set(mod, new Set());
    byModule.get(mod).add(name);
  }
  for (const [mod, names] of byModule) {
    src = ensureImport(src, names, importPath(file, mod));
  }
  stats.files += 1;
  if (!DRY) writeFileSync(file, src);
}

console.log(
  `${DRY ? "[dry-run] " : ""}konvertiert=${stats.converted} Dateien=${stats.files} ` +
    `davon block=${stats.block} ` +
    `uebersprungen(klassenausdruck)=${stats.skippedExprClass} uebersprungen(checkbox/…)=${stats.skippedType}`
);
if (REPORT && skipDetail.length) {
  console.log("--- nicht konvertiert (className ist ein Ausdruck) ---");
  for (const line of skipDetail.slice(0, 40)) console.log(line);
}