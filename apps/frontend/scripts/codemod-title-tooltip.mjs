#!/usr/bin/env node
/**
 * Migrate native `title=` on <button> to the Tooltip primitive.
 *
 * Why a scanner and not a regex: the opening tag has to be found exactly. A
 * `title={a > b ? x : y}` expression contains a `>` that is not the end of
 * the tag, and attribute values legitimately contain quotes and braces. The
 * scan tracks quote state, template-literal state and brace depth, and only
 * treats `>` as the tag end when none of them are open.
 *
 * Wrapping is layout-safe because Tooltip uses cloneElement and renders only
 * `<>child + portal</>` — no wrapper element enters the DOM, so flex and grid
 * parents of the button see exactly what they saw before.
 *
 * `title` is removed rather than kept alongside: leaving both would paint the
 * browser's own tooltip over ours.
 *
 * Spans are collected in one pass and applied back-to-front so earlier
 * replacements never invalidate a later offset.
 *
 * Run with --dry to print the plan without writing.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { findElements } from "./jsx-tags.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

/**
 * Locate a standalone `title=` inside the opening tag's attribute list.
 * Skips quoted strings and `{...}` expressions so a nested `title` inside a
 * string, or `aria-labelledby`-style neighbours, are not mistaken for it.
 */
function findTitleAttr(src, attrStart, tagEnd) {
  let i = attrStart;
  while (i < tagEnd) {
    const c = src[i];
    if (c === "'" || c === '"' || c === "`") {
      const q = c;
      i += 1;
      while (i < tagEnd && src[i] !== q) {
        if (src[i] === "\\") i += 1;
        i += 1;
      }
      i += 1;
      continue;
    }
    if (c === "{") {
      let depth = 1;
      i += 1;
      while (i < tagEnd && depth > 0) {
        if (src[i] === "{") depth += 1;
        else if (src[i] === "}") depth -= 1;
        i += 1;
      }
      continue;
    }
    if (src.startsWith("title=", i)) {
      const before = i > 0 ? src[i - 1] : "";
      if (before && /[A-Za-z0-9_-]/.test(before)) {
        i += 1;
        continue;
      }
      const valueStart = i + "title=".length;
      const vc = src[valueStart];
      let valueEnd;
      if (vc === "{") {
        let depth = 1;
        let j = valueStart + 1;
        while (j < tagEnd && depth > 0) {
          if (src[j] === "{") depth += 1;
          else if (src[j] === "}") depth -= 1;
          j += 1;
        }
        if (depth !== 0) return null;
        valueEnd = j;
      } else if (vc === '"' || vc === "'") {
        let j = valueStart + 1;
        while (j < tagEnd && src[j] !== vc) j += 1;
        valueEnd = j + 1;
      } else {
        return null;
      }
      return { value: src.slice(valueStart, valueEnd), start: i, end: valueEnd };
    }
    i += 1;
  }
  return null;
}

function lineStartOf(src, index) {
  return src.lastIndexOf("\n", index - 1) + 1;
}

function indentOf(src, index) {
  const ls = lineStartOf(src, index);
  const m = /^[ \t]*/.exec(src.slice(ls, index));
  return m ? m[0] : "";
}

/** Indent every line of the block except the first (which carries its own). */
function reindent(block, extra) {
  return block
    .split("\n")
    .map((line, idx) => (idx === 0 || line.trim() === "" ? line : extra + line))
    .join("\n");
}

/**
 * Remove a title attribute from an opening tag without leaving a hole.
 *
 * Two shapes matter. A title alone on its own line takes the whole line with it:
 * cutting only the attribute there leaves a blank line and, worse, an orphaned
 * `>` that reads like a syntax accident. An inline title leaves two spaces where
 * it sat, so the seam is collapsed to exactly one.
 *
 * Only the opening tag is passed in, so children keep their own indentation —
 * this function cannot reach them.
 */
function stripTitleFromOpenTag(tag, a, b) {
  const lineStart = tag.lastIndexOf("\n", a - 1) + 1;
  const lead = tag.slice(lineStart, a);
  const nl = tag.indexOf("\n", b);
  const rest = nl === -1 ? tag.slice(b) : tag.slice(b, nl);
  if (/^[ \t]*$/.test(lead) && /^[ \t]*$/.test(rest)) {
    return tag.slice(0, lineStart) + tag.slice(nl === -1 ? b : nl + 1);
  }
  return (
    tag.slice(0, a).replace(/[ \t]+$/, "") + tag.slice(b).replace(/^[ \t]+/, " ")
  );
}

function importPathFor(file) {
  const rel = relative(dirname(file), join(SRC, "ui", "Tooltip")).split(sep).join("/");
  return rel.startsWith(".") ? rel : `./${rel}`;
}

/**
 * Insert the Tooltip import after the last import STATEMENT, not after the last
 * line that starts with `import`. A multi-line `import {\n  A,\n} from "x"` has
 * its first line matching `^\s*import` while the statement is still open — splicing
 * there puts the new import inside the braces and breaks the parse.
 */
function endOfLastImport(lines) {
  let last = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (!/^\s*import\b/.test(lines[i])) continue;
    let depth = 0;
    for (let j = i; j < lines.length; j += 1) {
      const l = lines[j];
      for (const ch of l) {
        if (ch === "{") depth += 1;
        else if (ch === "}") depth -= 1;
      }
      const closed = depth <= 0;
      const hasSource = /from\s*["']/.test(l) || /^\s*import\s+["']/.test(l);
      if (closed && hasSource) {
        last = j;
        break;
      }
    }
  }
  return last;
}

function ensureImport(src, path) {
  const stmt = `import { Tooltip } from "${path}";`;
  if (src.includes(stmt)) return src;
  const lines = src.split("\n");
  const last = endOfLastImport(lines);
  if (last === -1) return `${stmt}\n${src}`;
  lines.splice(last + 1, 0, stmt);
  return lines.join("\n");
}

/**
 * Collect every <button> that carries a standalone title attribute.
 * findElements enforces the delimiter after the tag name, so <buttonbar> is not
 * swept up alongside the real buttons.
 */
function collect(src) {
  const found = [];
  for (const { tagStart, tagEnd, selfClosing } of findElements(src, "button")) {
    const title = findTitleAttr(src, tagStart + "<button".length, tagEnd);
    if (!title) continue;
    let blockEnd;
    if (selfClosing) {
      blockEnd = tagEnd;
    } else {
      const close = src.indexOf("</button>", tagEnd);
      if (close === -1) continue;
      blockEnd = close + "</button>".length;
    }
    found.push({ tagStart, tagEnd, blockEnd, title });
  }
  return found;
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (p.endsWith(".tsx") && !SKIP.some((r) => r.test(p))) yield p;
  }
}

export async function migrateTitleToTooltip({ dry = false } = {}) {
  const plan = [];
  let files = 0;
  let total = 0;

  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    const hits = collect(src);
    if (!hits.length) continue;

    let out = src;
    // Back-to-front so each replacement leaves earlier offsets untouched.
    for (const hit of [...hits].reverse()) {
      const indent = indentOf(out, hit.tagStart);
      const tag = out.slice(hit.tagStart, hit.tagEnd);
      const children = out.slice(hit.tagEnd, hit.blockEnd);
      const openTag = stripTitleFromOpenTag(
        tag,
        hit.title.start - hit.tagStart,
        hit.title.end - hit.tagStart,
      );
      // tagStart points AT the `<`, so the prefix already carries the trigger's
      // indentation. Repeating it on the opening line would double it — the
      // closing tag starts a fresh line and does need it.
      const wrapped =
        `<Tooltip label=${hit.title.value}>\n` +
        reindent(indent + openTag + children, "  ") +
        `\n${indent}</Tooltip>`;
      out = out.slice(0, hit.tagStart) + wrapped + out.slice(hit.blockEnd);
      plan.push({
        file,
        line: src.slice(0, hit.tagStart).split("\n").length,
        label: hit.title.value.replace(/\s+/g, " ").slice(0, 58),
      });
    }

    out = ensureImport(out, importPathFor(file));
    files += 1;
    total += hits.length;
    if (!dry) await writeFile(file, out);
  }
  return { files, total, plan };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const dry = process.argv.includes("--dry");
  migrateTitleToTooltip({ dry })
    .then(({ files, total, plan }) => {
      console.log(`${dry ? "[dry] " : ""}title->Tooltip: ${total} Buttons in ${files} Dateien`);
      if (dry) {
        for (const p of plan) console.log(`  ${p.file}:${p.line}  label=${p.label}`);
      }
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}
