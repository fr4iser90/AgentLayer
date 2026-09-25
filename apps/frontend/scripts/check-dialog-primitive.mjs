#!/usr/bin/env node
/**
 * Dialog-primitive guard.
 *
 * `ui/Modal.tsx` was written after measuring 16 overlays that each redrew the
 * same thing: a scrim, a panel, `role="dialog"`, `aria-modal="true"`. Eleven of
 * the sixteen had a dialog role and no Escape handler, and none trapped focus —
 * so a keyboard user could tab out of the dialog into the page behind it while
 * the app was still treating input as blocked. That is not a cosmetic drift, it
 * is the reason the primitive exists.
 *
 * Ten overlays moved onto Modal, three onto Drawer (they were side panels wearing
 * a modal's role), and five stayed hand-rolled on purpose: two full-screen
 * takeovers, one bottom sheet on mobile, one docked panel that is `md:static`
 * from `sm` up, and one content panel. Those five are recorded in
 * `dialog-baseline.json` with the reason each one is not a dialog.
 *
 * The rule is an allow-list, not a deny-list: dialog semantics on a DOM element
 * fail unless the file is the primitive itself or is recorded. A new overlay
 * gets Modal or an argument in the baseline, never a quiet pass.
 *
 * Two kinds are scanned:
 *   dialog — `role="dialog"`, `role="alertdialog"`, `aria-modal` on a lowercase
 *            element. On a component (`<Modal role="alertdialog">`) passing the
 *            role through is the supported way to vary it, so that is not a hit.
 *   scrim  — a class string holding `fixed` and `inset-0` together, i.e. code
 *            taking over the viewport. Modal and Drawer are the only two that
 *            should own this.
 *
 * Run with --explain to print the distribution.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");
const BASELINE = join(__dirname, "dialog-baseline.json");

const SCAN_EXT = [".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];

// The primitives are exempt by name, not by baseline: a baseline entry for the
// file that defines the behaviour would let a second implementation hide in it.
const PRIMITIVES = ["Modal.tsx", "Drawer.tsx"];

const ROLE_RE = /role\s*=\s*["'{]+(alertdialog|dialog)\b/g;
const ARIA_MODAL_RE = /aria-modal\s*[=\/>]/g;
// `fixed` and `inset-0` in one class string = viewport takeover. Both must be
// whole classes: `fixed inset-0` matches, `notfixed`/`inset-0x` do not.
// Template literals may span lines (a wrapped `cn(...)` list); a double-quoted
// string with a newline in it is not a class list, it is prose, so it stays
// single-line to keep quote pairing sane across JSX text.
const CLASS_STRING_RE = /"([^"\n]*)"|`([^`]*)`/g;

/**
 * Name of the tag an attribute position sits in, by walking back to the nearest
 * `<` that is followed by a tag-name start. Walking back rather than forward
 * avoids the `>` inside `onClick={() => a > b}` that a forward scan would treat
 * as the tag end. A `<` used as a comparison operator is followed by a space or
 * an operand, so it is skipped and the walk continues to the real tag.
 */
export function tagAt(src, pos) {
  for (let i = pos - 1; i >= 0; i -= 1) {
    if (src[i] !== "<") continue;
    const next = src[i + 1] ?? "";
    if (/[A-Za-z_]/.test(next)) {
      const m = /^<([A-Za-z][A-Za-z0-9.]*)/.exec(src.slice(i, pos + 1));
      return m ? m[1] : null;
    }
  }
  return null;
}

/**
 * Pure scan of one source string — exported so the matcher itself is testable.
 * A blind spot here does not report "I stopped seeing dialogs", it reports
 * "dialogs are clean", which is the difference between a gate and a decoration.
 */
export function scanDialogs(src) {
  const found = [];
  const lineOf = (pos) => src.slice(0, pos).split("\n").length;

  ROLE_RE.lastIndex = 0;
  let m;
  while ((m = ROLE_RE.exec(src)) !== null) {
    const tag = tagAt(src, m.index);
    // A component receiving `role` is the primitive's own prop, not a redraw.
    if (tag && /^[A-Z]/.test(tag)) continue;
    found.push({ kind: "dialog", cls: `role="${m[1]}"`, tag, line: lineOf(m.index) });
  }

  ARIA_MODAL_RE.lastIndex = 0;
  while ((m = ARIA_MODAL_RE.exec(src)) !== null) {
    const tag = tagAt(src, m.index);
    if (tag && /^[A-Z]/.test(tag)) continue;
    found.push({ kind: "dialog", cls: "aria-modal", tag, line: lineOf(m.index) });
  }

  CLASS_STRING_RE.lastIndex = 0;
  while ((m = CLASS_STRING_RE.exec(src)) !== null) {
    const cls = m[1] ?? m[2] ?? "";
    if (!/\bfixed\b/.test(cls) || !/\binset-0\b/.test(cls)) continue;
    found.push({ kind: "scrim", cls: "fixed inset-0", tag: null, line: lineOf(m.index) });
  }

  return found;
}

export async function checkDialogPrimitive() {
  const baseline = await readBaseline();
  const findings = [];
  const kept = [];
  const kinds = new Map();
  let total = 0;

  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file).split("\\").join("/");
    if (PRIMITIVES.some((p) => rel.endsWith(`/ui/${p}`))) continue;
    const issues = scanDialogs(await readFile(file, "utf8"));
    if (!issues.length) continue;
    const open = [];
    for (const i of issues) {
      const key = `${rel}::${i.kind}`;
      if (Object.prototype.hasOwnProperty.call(baseline, key)) {
        kept.push(key);
        continue;
      }
      total += 1;
      kinds.set(i.kind, (kinds.get(i.kind) ?? 0) + 1);
      open.push(i);
    }
    if (open.length) findings.push({ file: rel, issues: open });
  }

  const stale = Object.keys(baseline).filter((k) => !kept.includes(k));
  return { ok: findings.length === 0, findings, total, kinds, stale, baseline };
}

async function readBaseline() {
  try {
    const parsed = JSON.parse(await readFile(BASELINE, "utf8"));
    return parsed.overlays ?? {};
  } catch {
    return {};
  }
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

const WHY = {
  dialog:
    "Dialog-Semantik auf einem DOM-Element — Modal/Drawer haben den Fokus-Trap und Escape, ein eigenes <div role=\"dialog\"> nicht",
  scrim:
    "feste Viewport-Übernahme — `fixed inset-0` gehört in Modal oder Drawer, nicht an eine Seite",
};

async function main() {
  const result = await checkDialogPrimitive();

  if (process.argv.includes("--update")) {
    const all = { ...result.baseline };
    for (const k of result.stale) delete all[k];
    for (const { file, issues } of result.findings)
      for (const i of issues) all[`${file}::${i.kind}`] = "TODO — warum ist die Stelle kein Dialog?";
    await writeFile(
      BASELINE,
      `${JSON.stringify(
        {
          note: "Overlays, die bewusst nicht Modal/Drawer sind. Der Wert ist die Begründung, nicht ein Platzhalter — ein Eintrag ohne Grund ist eine Erlaubnis ohne Argument.",
          overlays: Object.fromEntries(Object.keys(all).sort().map((k) => [k, all[k]])),
        },
        null,
        2
      )}\n`
    );
    console.log(`[dialog] baseline geschrieben: ${Object.keys(all).length} Overlay(s)`);
    return;
  }

  if (process.argv.includes("--explain")) {
    const recorded = Object.keys(result.baseline);
    console.log(`[dialog] ${result.total} neue Verstoß/Verstöße, ${recorded.length} aufgezeichnet:`);
    for (const [k, n] of [...result.kinds.entries()].sort((a, b) => b[1] - a[1]))
      console.log(`  ${String(n).padStart(4)}  ${k}`);
    for (const k of recorded) console.log(`  alt  ${k}\n       ${result.baseline[k]}`);
    return;
  }

  if (!result.ok || result.stale.length) {
    if (!result.ok) {
      console.error(
        `[dialog] ${result.total} handgebaute Dialog-/Overlay-Stelle(n) in ${result.findings.length} Datei(en).`
      );
      for (const { file, issues } of result.findings) {
        console.error(`  ${file}`);
        for (const i of issues.slice(0, 8)) console.error(`    L${i.line} ${i.cls} — ${WHY[i.kind]}`);
        if (issues.length > 8) console.error(`    … +${issues.length - 8} mehr`);
      }
      console.error(
        "\n[dialog] <Modal> für zentrierte Dialoge, <Drawer> für Seitenpanels — beide trappen Fokus und schließen mit Escape."
      );
      console.error(
        "[dialog] Ist die Stelle wirklich kein Dialog? `npm run lint:dialog:update` und den Grund in den Commit."
      );
    }
    // A recorded overlay with no finding is a permission with no place behind it.
    if (result.stale.length)
      console.error(
        `[dialog] ${result.stale.length} Baseline-Eintrag(e) ohne Fund — löschen, sonst ist die Liste eine Erlaubnis ohne Stelle:`
      );
    for (const k of result.stale) console.error(`  ${k}`);
    process.exit(1);
  }

  const counts = await countPrimitives();
  console.log(
    `[dialog] OK - ${counts.modal} Modal- und ${counts.drawer} Drawer-Nutzung(en), keine neue Handarbeit. ${Object.keys(result.baseline).length} Overlay(s) aufgezeichnet.`
  );
}

async function countPrimitives() {
  let modal = 0;
  let drawer = 0;
  for await (const file of walk(SRC)) {
    const text = await readFile(file, "utf8");
    modal += (text.match(/<Modal\b/g) ?? []).length;
    drawer += (text.match(/<Drawer\b/g) ?? []).length;
  }
  return { modal, drawer };
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}