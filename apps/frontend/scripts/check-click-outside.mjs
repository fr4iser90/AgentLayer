#!/usr/bin/env node
/**
 * Click-outside guard.
 *
 * `ui/useClickOutside.ts` replaced five verbatim copies of a dismissal
 * listener. Four of them survived the primitive and are only gone now: three
 * listened to `mousedown`, one to `pointerdown`, two had no Escape handler, and
 * the `mousedown` variants had a bug nobody had filed — a tap on a touch device
 * arrives as `pointerdown` and then a synthesised `mousedown`, which closed a
 * menu and reopened it in the same gesture.
 *
 * The rule is narrow on purpose. Only pointer events bound on `document` count,
 * because that is the shape of a dismissal listener:
 *
 *   document.addEventListener("mousedown", …)   ← a copy of the hook
 *   window.addEventListener("pointermove", …)   ← a drag, legitimate, not flagged
 *   document.addEventListener("keydown", …)     ← a shortcut, legitimate, not flagged
 *
 * `keydown` stays free: Escape belongs to the hook for anchored popovers, but
 * Tooltip, the lightbox and the canvas all own real keyboard shortcuts and are
 * not popovers.
 *
 * There is no baseline. The tree is at zero, and a baseline here would only be
 * a place to park a copy until nobody looks.
 */
import { readFile, readdir } from "node:fs/promises";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

const SCAN_EXT = [".ts", ".tsx", ".jsx"];
const SKIP = [/node_modules/, /\.test\./, /\.snap$/];
const OWNER = "src/ui/useClickOutside.ts";

// The events that mean "the pointer went somewhere else". `mousemove` and
// `pointermove` are excluded: on document they are drags and tracking, not
// dismissal, and flagging them would push callers toward a worse listener.
const POINTER_EVENTS = new Set([
  "mousedown",
  "mouseup",
  "click",
  "dblclick",
  "pointerdown",
  "pointerup",
  "touchstart",
  "touchend",
]);

const LISTENER_RE = /\bdocument\s*\.\s*addEventListener\s*\(\s*["']([a-z]+)["']/g;

/**
 * Pure scan of one source string — exported so the matcher is testable. A
 * blind spot here reports "no copies left", which is exactly the message that
 * was true the whole time four of them were.
 */
export function scanClickOutside(src) {
  const found = [];
  LISTENER_RE.lastIndex = 0;
  let m;
  while ((m = LISTENER_RE.exec(src)) !== null) {
    const event = m[1];
    if (!POINTER_EVENTS.has(event)) continue;
    found.push({ event, line: src.slice(0, m.index).split("\n").length });
  }
  return found;
}

export async function checkClickOutside() {
  const findings = [];
  let total = 0;
  for await (const file of walk(SRC)) {
    const rel = relative(ROOT, file).split("\\").join("/");
    if (rel === OWNER) continue;
    const issues = scanClickOutside(await readFile(file, "utf8"));
    if (!issues.length) continue;
    total += issues.length;
    findings.push({ file: rel, issues });
  }
  return { ok: findings.length === 0, findings, total };
}

async function* walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else if (SCAN_EXT.some((x) => p.endsWith(x)) && !SKIP.some((r) => r.test(p))) yield p;
  }
}

async function main() {
  const { ok, findings, total } = await checkClickOutside();
  if (!ok) {
    console.error(
      `[click-outside] ${total} eigene Wegklapp-Listener in ${findings.length} Datei(en) — die hat useClickOutside.`
    );
    for (const { file, issues } of findings) {
      console.error(`  ${file}`);
      for (const i of issues.slice(0, 8))
        console.error(
          `    L${i.line} document.addEventListener("${i.event}") — mousedown feuert doppelt bei einem Tap`
        );
      if (issues.length > 8) console.error(`    … +${issues.length - 8} mehr`);
    }
    console.error("\n[click-outside] useClickOutside(ref, close, open) — pointerdown plus Escape, ein Listener pro Popover.");
    process.exit(1);
  }
  console.log(`[click-outside] OK - kein Popover hört selbst auf die document. useClickOutside ist der einzige Besitzer.`);
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}