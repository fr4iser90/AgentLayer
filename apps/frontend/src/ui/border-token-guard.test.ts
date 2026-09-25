import { describe, expect, it } from "vitest";
import { colourStem, scanBorders } from "../../scripts/check-border-token.mjs";

const kinds = (src: string) => scanBorders(src).map((f) => f.kind);
const classes = (src: string) => scanBorders(src).map((f) => f.cls);

describe("border colour stem is not a width", () => {
  it("reads a directional width utility as geometry, not an unknown colour", () => {
    // `md:border-y-0` failed a real build: the stem came out `y-0`, which is in
    // neither the token set nor GEOMETRY (which holds `0`), so a width utility
    // was reported as a border COLOUR decision.
    expect(scanBorders(`"absolute inset-x-0 bottom-0 w-full border-y-0"`)).toEqual([]);
    expect(scanBorders(`"md:border-y-0"`)).toEqual([]);
    expect(scanBorders(`"border-x-2 border-t-4 border-l-8"`)).toEqual([]);
    expect(scanBorders(`"border-y-none border-x-dashed"`)).toEqual([]);
  });

  it("still reads a directional COLOUR as a colour", () => {
    // The other half of the rule. Stripping the direction must not turn
    // `border-y-white` into something the guard stops seeing — that would
    // trade a false positive for a bypass.
    expect(kinds(`"border-y-white/10"`)).toEqual(["grey/white hairline"]);
    expect(kinds(`"border-x-sky-500"`)).toEqual(["foreign semantic"]);
    expect(classes(`"md:border-y-white/10"`)).toEqual(["md:border-y-white/10"]);
  });

  it("does not strip a direction letter out of a token name", () => {
    // `line-strong` starts with `l`, which is also a direction letter. Only a
    // lone letter followed by a hyphen may be stripped.
    expect(colourStem("border-line-strong")).toBe("line-strong");
    expect(colourStem("border-line-subtle")).toBe("line-subtle");
    expect(scanBorders(`"rounded-card border border-line-strong"`)).toEqual([]);
    expect(colourStem("border-y-line")).toBe("line");
    expect(scanBorders(`"border-y-line"`)).toEqual([]);
  });
});

describe("border guard keeps seeing what it always saw", () => {
  it("flags greyscale and foreign colours", () => {
    expect(kinds(`"border border-white/10"`)).toEqual(["grey/white hairline"]);
    expect(kinds(`"border border-neutral-400"`)).toEqual(["grey/white hairline"]);
    expect(kinds(`"border border-red-500"`)).toEqual(["foreign semantic"]);
  });

  it("flags a variant-prefixed hairline", () => {
    expect(classes(`"hover:border-white/10"`)).toEqual(["hover:border-white/10"]);
    expect(classes(`"md:focus:border-neutral-300"`)).toEqual(["md:focus:border-neutral-300"]);
  });

  it("accepts the line tokens", () => {
    expect(scanBorders(`"border border-line border-t-line-subtle"`)).toEqual([]);
    expect(scanBorders(`"focus:border-line-focus"`)).toEqual([]);
    expect(scanBorders(`"border border-transparent"`)).toEqual([]);
  });
});