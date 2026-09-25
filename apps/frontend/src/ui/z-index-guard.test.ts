import { describe, expect, it } from "vitest";
import { scanZIndexes } from "../../scripts/check-z-index.mjs";

const kinds = (src: string) => scanZIndexes(src).map((f) => f.kind);
const count = (src: string) => scanZIndexes(src).length;
// The reported class has to be the one a reader can find in the file. A report
// of `z-z-50` counts correctly and points nowhere, and only this assertion
// catches it.
const cls = (src: string) => scanZIndexes(src).map((f) => f.cls);
const lines = (src: string) => scanZIndexes(src).map((f) => f.line);

describe("guard sees raw stacking", () => {
  it("flags a bare numeric level", () => {
    expect(count(`"fixed inset-0 z-50"`)).toBe(1);
    expect(kinds(`"fixed inset-0 z-50"`)).toEqual(["raw"]);
    expect(cls(`"fixed inset-0 z-50"`)).toEqual(["z-50"]);
    expect(count(`"absolute z-10 z-20 z-30"`)).toBe(3);
  });

  it("reports the variant chain it matched, not a rebuilt one", () => {
    expect(cls(`"sm:focus:z-10"`)).toEqual(["sm:focus:z-10"]);
    expect(cls(`"md:!z-50"`)).toEqual(["md:!z-50"]);
    expect(cls(`"-z-lift"`)).toEqual(["-z-lift"]);
  });

  it("flags an arbitrary value", () => {
    expect(kinds(`"z-[999]"`)).toEqual(["arbitrary"]);
    expect(count(`"relative z-[7] mt-snug"`)).toBe(1);
  });

  it("flags z-[1] — the bracket boundary an anchored scan misses", () => {
    // `\b` after the closing bracket finds nothing here: `]` and the following
    // space are both non-word, so there is no boundary to anchor on. An earlier
    // grep using `\b` reported no arbitrary values while the tree held four.
    expect(count(`"relative z-[1] mt-snug"`)).toBe(1);
    expect(count(`"z-[1]"`)).toBe(1);
    expect(count(`"flex z-[1] items-center justify-center"`)).toBe(1);
  });

  it("flags the variant-prefix chain", () => {
    // Anchoring on whitespace alone hides every prefixed class.
    expect(count(`"hover:z-50"`)).toBe(1);
    expect(count(`"sm:focus:z-10"`)).toBe(1);
    expect(count(`"group-hover:md:z-[999]"`)).toBe(1);
  });

  it("flags the important modifier and a negative level", () => {
    expect(count(`"md:!z-50"`)).toBe(1);
    expect(kinds(`"!z-[9]"`)).toEqual(["arbitrary"]);
    // `-z-lift` names a real token, but the scale has no negative step, so it
    // renders nothing — a token match must not be mistaken for a legal class.
    expect(kinds(`"-z-lift"`)).toEqual(["negative"]);
    expect(kinds(`"md:-z-modal"`)).toEqual(["negative"]);
  });

  it("flags a name that is not in the scale", () => {
    // A typo renders no CSS at all: the layer silently loses its stacking.
    expect(kinds(`"z-tooptip"`)).toEqual(["unknown"]);
    expect(kinds(`"z-sheet"`)).toEqual(["unknown"]);
  });

  it("flags an inline style, which never touches the theme", () => {
    expect(kinds(`<div style={{ zIndex: 50 }} />`)).toEqual(["inline"]);
    expect(kinds(`const s: CSSProperties = { zIndex: 100 };`)).toEqual(["inline"]);
  });

  it("sees a violation in the form the guard actually reads", () => {
    // Whole-file text, a bare const string, one violation per level present.
    const file = [
      `const WRAP = "fixed inset-0 z-[100] flex items-center justify-center";`,
      `const PANEL = "relative z-30 rounded-card bg-card";`,
      `export function Overlay() {`,
      `  return <div className={\`\${WRAP} hover:z-50\`}><span className="z-modal" /></div>;`,
      `}`,
    ].join("\n");
    expect(count(file)).toBe(3);
    expect(kinds(file)).toEqual(["arbitrary", "raw", "raw"]);
    // Each finding must name the line it came from, not the first line that
    // happens to contain the same class.
    expect(lines(file)).toEqual([1, 2, 4]);
    expect(cls(file)).toEqual(["z-[100]", "z-30", "hover:z-50"]);
  });
});

describe("named levels are invisible", () => {
  it("does not flag the tokens in tailwind.config.js", () => {
    expect(count(`"fixed inset-0 z-modal flex items-center justify-center"`)).toBe(0);
    expect(count(`"absolute z-lift z-docked z-canvas z-menu z-overlay z-tooltip"`)).toBe(0);
  });

  it("does not flag z-auto, including responsive", () => {
    // md:z-auto switches a mobile-only layer back to normal flow.
    expect(count(`"fixed inset-0 z-modal md:z-auto"`)).toBe(0);
  });

  it("does not flag a prefixed token", () => {
    expect(count(`"hover:z-lift sm:focus:z-menu"`)).toBe(0);
    expect(count(`"md:!z-modal"`)).toBe(0);
  });

  it("every level in the scale is invisible to the guard", async () => {
    // The allow-list and the rendered scale must be the same list. If the guard
    // kept its own copy, renaming a token would leave it flagging live code.
    const config = (await import("../../tailwind.config.js")).default;
    for (const name of Object.keys(config.theme.zIndex)) {
      expect(count(`"relative z-${name} hover:z-${name}"`)).toBe(0);
    }
  });
});

describe("matcher must not over-match", () => {
  it("does not flag a bracket value on another property", () => {
    expect(count(`"w-[320px] text-[11px] leading-[1.5]"`)).toBe(0);
    expect(count(`"grid-cols-[repeat(2,minmax(0,1fr))]"`)).toBe(0);
  });

  it("does not flag a class that merely contains z", () => {
    expect(count(`"rotate-45 blur-sm duration-150 ease-standard"`)).toBe(0);
    expect(count(`"text-ink-on-fill bg-canvas"`)).toBe(0);
  });

  it("does not flag the word zIndex outside a style key", () => {
    expect(count(`// stacking is not spelled zIndex here`)).toBe(0);
  });
});

describe("the scale itself keeps the properties the guard assumes", () => {
  it("replaces Tailwind's defaults instead of adding to them", async () => {
    // This is the part a guard cannot do: with the scale at theme level, z-50
    // emits no CSS, so a raw level is unrenderable rather than merely reported.
    const config = (await import("../../tailwind.config.js")).default;
    expect(config.theme.zIndex).toBeDefined();
    expect(config.theme.extend?.zIndex).toBeUndefined();
  });

  it("orders the levels the way the layer roles require", async () => {
    const config = (await import("../../tailwind.config.js")).default;
    const n = (k: string) => Number(config.theme.zIndex[k]);
    expect(n("lift")).toBeLessThan(n("canvas"));
    expect(n("canvas")).toBeLessThan(n("docked"));
    expect(n("docked")).toBeLessThan(n("menu"));
    expect(n("menu")).toBeLessThan(n("overlay"));
    expect(n("overlay")).toBeLessThan(n("modal"));
    // The tooltip is the only portaled layer, so it must clear every dialog.
    expect(n("modal")).toBeLessThan(n("tooltip"));
  });
});