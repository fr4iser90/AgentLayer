#!/usr/bin/env node
/**
 * Primitive-coverage guard.
 *
 * `src/ui/` is a promise, not a folder: a component that sits there claims to be
 * the way the app does that thing. A primitive nobody imports makes the promise
 * false in a way that is invisible from the outside — the file compiles, its own
 * tests pass, and the surfaces next to it keep hand-drawing the control. Twenty
 * files in `src/ui/` and no record of which of them the app actually stands on.
 *
 * So the rule is dull and checkable: every `src/ui/*.tsx` must have at least one
 * importer somewhere else in `src/`. That is the difference between a design
 * system and a pile of well-named components, and it is the only part of the
 * claim that a machine can confirm without a screenshot.
 *
 * Importers are resolved from the specifier, not from the exported name: the
 * repo has no `src/ui/index.ts` and callers write `../ui/Button`, so matching on
 * `from "./Button"` after resolving the path is both exact and independent of a
 * barrel that does not exist. Adding a barrel later would not weaken this — the
 * barrel itself becomes an importer of every module and the guard says so, which
 * is precisely the moment to notice that nothing outside `src/ui/` uses it.
 *
 * An exception is not a baseline entry: `NOT_FOR_REUSE` names a module and the
 * reason it is exempt, and a reason that stops naming anything in the tree is a
 * lie about the tree, so it fails.
 */
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { stripComments } from "./strip-comments.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const UI = "src/ui";

const SCAN_EXT = [".tsx", ".jsx", ".ts"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

/**
 * Modules that live in `src/ui/` without claiming to be reusable surfaces.
 *
 * `Toast.tsx` exports the provider, the hook and two timing constants; the
 * constants are read by `Toast.tsx` itself and by nothing else, which is correct
 * for a module that owns a timer and would be a violation of this guard if the
 * rule asked about exports instead of about modules.
 */
const NOT_FOR_REUSE = new Set();

const IMPORT_FROM = /\bfrom\s*"(\.[^"]*)"|\bimport\s*\(\s*"(\.[^"]*)"/g;

export async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

/** Every relative specifier in a source string, in the order they appear. */
export function scanSpecifiers(src) {
  const out = [];
  for (const m of stripComments(src).matchAll(IMPORT_FROM)) out.push(m[1] ?? m[2]);
  return out;
}

/**
 * Resolves a relative specifier to a repo-relative module path without
 * extension, or `null` when it points outside `src/`.
 *
 * `./Button` from `src/ui/Menu.tsx` and `../ui/Button` from `src/pages/X.tsx`
 * must land on the same key, otherwise a primitive could be imported by every
 * file in the app and still look unused.
 */
export function resolveSpecifier(fromFileRel, specifier) {
  const abs = resolve(SRC, "..", dirname(fromFileRel), specifier);
  const rel = relative(ROOT, abs).split("\\").join("/");
  return rel.startsWith("src/") ? rel.replace(/\.(tsx|jsx|ts)$/, "") : null;
}

/**
 * Pure core: which ui modules does nothing import?
 *
 * `files` is `[{ rel, specifiers }]`. Self-imports do not count — a module that
 * only ever appears in its own file is exactly the orphan this guard is for, and
 * counting a `from "./Button"` inside `Button.tsx` (which never happens, but the
 * matcher would allow it) would hide it.
 */
export function findOrphans(files, uiDir = UI) {
  const modules = files.filter((f) => f.rel.startsWith(`${uiDir}/`) && /\.tsx$/.test(f.rel));
  const importers = new Map();
  for (const file of files) {
    for (const spec of file.specifiers) {
      const target = resolveSpecifier(file.rel, spec);
      if (!target) continue;
      if (target === file.rel.replace(/\.tsx$/, "")) continue;
      if (!importers.has(target)) importers.set(target, new Set());
      importers.get(target).add(file.rel);
    }
  }
  return modules
    .filter((m) => !NOT_FOR_REUSE.has(m.rel))
    .map((m) => ({
      module: m.rel,
      fromUi: [...(importers.get(m.rel.replace(/\.tsx$/, "")) ?? [])].filter((f) =>
        f.startsWith(`${uiDir}/`)
      ),
      fromApp: [...(importers.get(m.rel.replace(/\.tsx$/, "")) ?? [])].filter(
        (f) => !f.startsWith(`${uiDir}/`)
      ),
    }))
    .filter((m) => m.fromUi.length + m.fromApp.length === 0);
}

async function scanTree() {
  const files = [];
  for await (const file of walk(SRC)) {
    const src = await readFile(file, "utf8");
    files.push({ rel: relative(ROOT, file).split("\\").join("/"), specifiers: scanSpecifiers(src) });
  }
  return files;
}

/**
 * Consumer count per ui module: how many *other* files import it.
 *
 * The pass/fail rule only asks for "at least one", so the plain run cannot
 * answer how much of this system is load-bearing — one importer and forty both
 * pass. `--report` prints both columns.
 */
export function countConsumers(files, uiDir = UI) {
  const importers = new Map();
  for (const file of files) {
    for (const spec of file.specifiers) {
      const target = resolveSpecifier(file.rel, spec);
      if (!target) continue;
      if (target === file.rel.replace(/\.[^.]+$/, "")) continue;
      if (!importers.has(target)) importers.set(target, new Set());
      importers.get(target).add(file.rel);
    }
  }
  return files
    .filter((f) => f.rel.startsWith(`${uiDir}/`) && /\.tsx$/.test(f.rel))
    .map((f) => {
      const set = importers.get(f.rel.replace(/\.tsx$/, "")) ?? new Set();
      const outside = [...set].filter((x) => !x.startsWith(`${uiDir}/`));
      return { module: f.rel, outside: outside.length, inside: set.size - outside.length };
    })
    .sort((a, b) => b.outside + b.inside - (a.outside + a.inside) || a.module.localeCompare(b.module));
}

export async function checkPrimitiveCoverage() {
  const files = await scanTree();
  const orphans = findOrphans(files);
  const covered = files.filter((f) => f.rel.startsWith(`${UI}/`) && /\.tsx$/.test(f.rel)).length;
  return { orphans, covered, exempt: [...NOT_FOR_REUSE] };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const reportAt = process.argv.indexOf("--report");
  if (reportAt >= 0) {
    const wanted = process.argv.slice(reportAt + 1).filter((a) => !a.startsWith("-"));
    scanTree()
      .then((files) => {
        const rows = countConsumers(files).filter(
          (r) => wanted.length === 0 || wanted.some((w) => r.module === `${UI}/${w}.tsx`)
        );
        for (const r of rows) {
          console.log(
            `${r.outside >= 1 ? "OK  " : "FAIL"} ${r.module} Consumenten aussen=${r.outside} innerhalb src/ui=${r.inside}`
          );
        }
        const missing = rows.filter((r) => r.outside === 0).length;
        console.log(
          `[primitive-coverage] ${rows.length} Modul(e), ${rows.reduce((n, r) => n + r.outside, 0)} Consument(en) ausserhalb von src/ui/, ${missing} ohne ausseren Consumenten.`
        );
        process.exit(missing ? 1 : 0);
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  } else {
    checkPrimitiveCoverage()
      .then(({ orphans, covered, exempt }) => {
        if (orphans.length) {
          console.error(
            `[primitive-coverage] FAILED - ${orphans.length} Primitive(n) in src/ui/ ohne jede Nutzung:`
          );
          for (const o of orphans) console.error(`  ${o.module}`);
          console.error(
            "[primitive-coverage] Entweder nutzt eine Fläche sie, oder sie gehört nicht in src/ui/. Begründete Ausnahmen in NOT_FOR_REUSE mit Grund."
          );
          process.exit(1);
        }
        console.log(
          `[primitive-coverage] OK - ${covered} Primitive(n) in src/ui/, jede mit mindestens einem Importeur außerhalb ihrer eigenen Datei${exempt.length ? `, ${exempt.length} begründet ausgenommen` : ""}.`
        );
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  }
}