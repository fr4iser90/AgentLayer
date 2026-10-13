import { describe, expect, it } from "vitest";
import { scanTextTokens, classify } from "../../scripts/check-ink-color.mjs";

const tokens = (src: string) => scanTextTokens(src);
const raw = (src: string) => scanTextTokens(src).filter((t) => classify(t) !== null);

describe("ink guard sees the shapes it must see", () => {
  it("flags a bare greyscale text colour", () => {
    expect(raw(`<div className="text-white">x</div>`)).toEqual(["white"]);
  });

  it("flags a foreign semantic colour at the END of a class string", () => {
    // `(?=\s|$)` alone never matches the last class in a string — a planted
    // `text-slate-300` walked straight through a guard that reported OK.
    expect(raw(`<div className="px-2 text-slate-300">x</div>`)).toEqual(["slate-300"]);
    expect(raw(`"text-slate-300"`)).toEqual(["slate-300"]);
  });

  it("admits the opacity modifier", () => {
    // Without `/` in the value class the lookahead fails at the slash and the
    // class does not exist: 206 of the tree's raw colours were opacity variants.
    expect(raw(`"text-red-500/50"`)).toEqual(["red-500/50"]);
    expect(raw(`"text-sky-400/90"`)).toEqual(["sky-400/90"]);
  });

  it("admits the variant-prefix chain", () => {
    // Third shape of the same defect in this file's lifetime. Anchoring on
    // whitespace alone left every prefixed class invisible.
    expect(raw(`"hover:text-sky-300"`)).toEqual(["sky-300"]);
    expect(raw(`"focus:text-amber-300/90"`)).toEqual(["amber-300/90"]);
    expect(raw(`"sm:hover:text-red-200"`)).toEqual(["red-200"]);
    expect(raw(`"group-hover:text-neutral-200"`)).toEqual(["neutral-200"]);
  });

  it("counts a prefixed and a bare occurrence of the same colour as two sightings", () => {
    expect(tokens(`"text-sky-300 hover:text-sky-300"`)).toHaveLength(2);
  });

  it("counts every raw colour on a line carrying several", () => {
    expect(raw(`"text-sky-300 px-2 text-amber-200"`)).toEqual(["sky-300", "amber-200"]);
  });
});

describe("compliant text is invisible", () => {
  it("accepts the ink scale", () => {
    expect(raw(`"text-ink-primary text-ink-muted text-ink-faint"`)).toEqual([]);
  });

  it("accepts semantic and badge tokens", () => {
    expect(raw(`"text-accent text-success text-warning text-danger"`)).toEqual([]);
    expect(raw(`"text-badge-accent text-badge-danger"`)).toEqual([]);
  });

  it("accepts a semantic token under a variant prefix", () => {
    expect(raw(`"hover:text-accent focus:text-ink-secondary"`)).toEqual([]);
  });

  it("accepts the keyword values", () => {
    expect(raw(`"text-transparent text-inherit text-current"`)).toEqual([]);
  });
});

describe("classification is per-kind, not one bucket", () => {
  it("separates greyscale from foreign semantics", () => {
    expect(classify("neutral-400")).toBe("greyscale");
    expect(classify("slate-300")).toBe("greyscale");
    expect(classify("sky-400")).toBe("foreign");
    expect(classify("rose-300")).toBe("foreign");
  });

  it("strips the opacity modifier before classifying", () => {
    expect(classify("red-500/50")).toBe("foreign");
    expect(classify("ink-muted/80")).toBeNull();
  });

  it("returns null for a token", () => {
    expect(classify("ink")).toBeNull();
    expect(classify("badge-warning")).toBeNull();
  });
});

describe("matcher must not over-match", () => {
  it("does not match a hue-less or malformed value", () => {
    expect(tokens(`"text-"`)).toEqual([]);
  });

  it("does not treat a longer word starting with text- as a colour", () => {
    // `text-label` and `text-meta` are type-scale tokens, not colours.
    expect(raw(`"text-label text-meta"`)).toEqual([]);
  });
});

// The guard used to scope itself to JSX tags. Every test above would have passed
// under that scoping, which is exactly why the scoping survived: the negative
// test was planted inside a tag and so proved nothing about the other 5 % of the
// tree. These pin the widening.
describe("scan covers the whole file, not only JSX tags", () => {
  it("sees a colour in a module-level class constant", () => {
    expect(raw(`const verdict = "text-emerald-300 bg-emerald-950/40";`)).toEqual([
      "emerald-300",
    ]);
  });

  it("sees a colour in a returned ternary with no JSX anywhere", () => {
    expect(raw(`function f(p) { return p >= 90 ? "text-emerald-300" : "text-rose-300"; }`)).toEqual([
      "emerald-300",
      "rose-300",
    ]);
  });

  it("sees a prefixed colour in a constant, the shape that used to slip twice", () => {
    expect(raw(`const idle = "text-ink-muted hover:text-neutral-200";`)).toEqual(["neutral-200"]);
  });
});

describe("comments are not code", () => {
  it("does not flag a colour named in a line comment", () => {
    expect(raw(`// was text-red-500 before the migration\n`)).toEqual([]);
  });

  it("does not flag a colour named in a block comment", () => {
    expect(raw(`/* use text-sky-400 here */\n`)).toEqual([]);
  });

  it("still flags a real class on the line after a comment", () => {
    expect(raw(`// note\nconst c = "text-sky-400";`)).toEqual(["sky-400"]);
  });

  it("does not mistake // inside a string for a comment start", () => {
    // A URL in an href must not blank the rest of the line and hide a class.
    expect(raw(`<a href="https://example.com" className="text-sky-400">x</a>`)).toEqual([
      "sky-400",
    ]);
  });
});