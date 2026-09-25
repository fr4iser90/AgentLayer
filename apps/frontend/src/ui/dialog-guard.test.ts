import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { checkDialogPrimitive, scanDialogs, tagAt } from "../../scripts/check-dialog-primitive.mjs";

/**
 * Same shape as the rest of the guard family: the matchers are pure and
 * exported, so what is tested here is the scanner's own eyes, not a fixture it
 * happens to like. Two directions matter most:
 *
 * - `<Modal role="alertdialog">` is the supported way to vary the role, so a
 *   component tag must not count. A guard that flagged it would be answered by
 *   widening the rule until it caught nothing.
 * - The primitives are exempt by name. If that exemption were doing all the
 *   work — i.e. the scanner could not see a hand-rolled dialog at all — the
 *   guard would report "clean" forever. One test scans Modal.tsx directly and
 *   requires it to find the hits the run then skips.
 */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const kinds = (src) => scanDialogs(src).map((i) => i.kind);

describe("tagAt", () => {
  it("reads the tag an attribute sits in", () => {
    expect(tagAt(`<div role="dialog">`, 5)).toBe("div");
    expect(tagAt(`<Modal\n  role="alertdialog"\n>`, 12)).toBe("Modal");
  });

  it("is not stopped by a > inside an arrow function", () => {
    const src = `<div onClick={() => count > 0} role="dialog">`;
    expect(tagAt(src, src.indexOf("role"))).toBe("div");
  });

  it("skips a < used as a comparison operator", () => {
    const src = `<section onPick={() => a < b} role="dialog">`;
    expect(tagAt(src, src.indexOf("role"))).toBe("section");
  });
});

describe("scanDialogs — dialog semantics", () => {
  it("flags a hand-rolled dialog role and aria-modal", () => {
    const found = scanDialogs(
      `<div role="dialog" aria-modal="true" className="p-4"><h2>Hi</h2></div>`
    );
    expect(found.map((i) => i.cls)).toEqual(['role="dialog"', "aria-modal"]);
    expect(found.every((i) => i.kind === "dialog")).toBe(true);
  });

  it("flags alertdialog", () => {
    expect(scanDialogs(`<div role="alertdialog" />`).map((i) => i.cls)).toEqual([
      'role="alertdialog"'
    ]);
  });

  it("accepts the role passed to a component", () => {
    expect(kinds(`<Modal role="alertdialog" describedBy="x" />`)).toEqual([]);
  });

  it("does not match a role that merely starts with dialog", () => {
    expect(kinds(`<div role="dialogue" aria-modalish="true" />`)).toEqual([]);
  });

  it("reports the line the violation is on", () => {
    const src = `const a = 1;\nconst b = 2;\n<div\n  role="dialog"\n/>`;
    expect(scanDialogs(src)[0].line).toBe(4);
  });
});

describe("scanDialogs — viewport takeover", () => {
  it("flags fixed inset-0 in one class string", () => {
    expect(kinds(`<div className="fixed inset-0 z-modal flex" />`)).toEqual(["scrim"]);
  });

  it("leaves an absolute scrim inside a panel alone", () => {
    expect(kinds(`<div className="absolute inset-0 bg-black/60" />`)).toEqual([]);
  });

  it("does not join fixed and inset-0 across two strings", () => {
    expect(kinds(`const A = "fixed";\nconst B = "inset-0";`)).toEqual([]);
  });

  it("does not match classes that merely contain them", () => {
    expect(kinds(`<div className="notfixed inset-0x" />`)).toEqual([]);
  });

  it("sees a takeover written across a wrapped template literal", () => {
    expect(kinds("const WRAP = `fixed inset-0\n  z-modal flex`;")).toEqual(["scrim"]);
  });
});

describe("checkDialogPrimitive", () => {
  it("passes the tree with nothing open", async () => {
    const r = await checkDialogPrimitive();
    expect(r.findings).toEqual([]);
    expect(r.total).toBe(0);
  });

  it("keeps the recorded overlays honest — no permission without a place", async () => {
    // A stale entry is a file listed as allowed to hand-roll an overlay that no
    // longer exists. Left in place, the list stops describing the tree.
    const r = await checkDialogPrimitive();
    expect(r.stale).toEqual([]);
  });

  it("sees the primitives' own dialogs, so the exemption is what skips them", async () => {
    // Without this, an exemption broad enough to hide Modal.tsx could also hide
    // every page that copied it, and the guard would report clean forever.
    const seen = [];
    for (const name of ["Modal.tsx", "Drawer.tsx"]) {
      const src = await readFile(join(ROOT, "src", "ui", name), "utf8");
      seen.push(...scanDialogs(src));
    }
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((i) => i.kind === "dialog" || i.kind === "scrim")).toBe(true);
  });
});