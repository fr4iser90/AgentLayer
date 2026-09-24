import { describe, expect, it } from "vitest";
import { scanWidths } from "../../scripts/check-content-width.mjs";
import { rewriteWidths, TOKENS } from "../../scripts/width-scan.mjs";

const scan = (src) => scanWidths(src);

describe("content-width guard recognises the ramp", () => {
  it("counts a config token as on-ramp", () => {
    const r = scan(`<div className="max-w-page">x</div>`);
    expect(r.total).toBe(1);
    expect(r.onToken).toBe(1);
  });

  it("flags a Tailwind default scale name", () => {
    const r = scan(`<div className="max-w-md">x</div>`);
    expect(r.offToken).toBe(1);
  });

  it("flags an arbitrary bracketed value", () => {
    const r = scan(`<div className="max-w-[37rem]">x</div>`);
    expect(r.offToken).toBe(1);
  });
});

// Both of these were real defects in the first version of the matcher, found by
// the total not matching an independent count. A matcher that silently sees
// fewer classes than exist makes the guard green while it guards nothing, so
// these assert the POPULATION rather than the verdict.
describe("matcher must not silently drop values", () => {
  it("sees a value with a leading digit (2xl, 6xl, 64)", () => {
    const r = scan(`<div className="max-w-2xl max-w-3xl max-w-6xl max-w-64">x</div>`);
    expect(r.total).toBe(4);
    expect(r.offToken).toBe(4);
  });

  it("sees a camelCase token the ramp actually writes", () => {
    const r = scan(`<div className="max-w-controlWide max-w-pageNarrow">x</div>`);
    expect(r.total).toBe(2);
    expect(r.onToken).toBe(2);
  });

  it("counts every token on a line that carries two of them", () => {
    const r = scan(`<div className={wide ? "max-w-4xl" : "max-w-2xl"}>x</div>`);
    expect(r.total).toBe(2);
  });
});

describe("matcher scope", () => {
  it("does not match min-w or max-h", () => {
    const r = scan(`<div className="min-w-0 max-h-64 max-w-md">x</div>`);
    expect(r.total).toBe(1);
  });

  it("does not match a longer tag that merely starts with max-w", () => {
    const r = scan(`<div className="max-widthish">x</div>`);
    expect(r.total).toBe(0);
  });

  it("keeps a responsive prefix and still flags the value", () => {
    const r = scan(`<div className="sm:max-w-lg">x</div>`);
    expect(r.total).toBe(1);
    expect(r.offToken).toBe(1);
    expect(r.values[0].token).toBe("sm:max-w-lg");
  });

  it("reaches a class hidden inside a template interpolation", () => {
    const r = scan("className={`flex ${compact ? \"max-w-md\" : \"max-w-page\"}`}");
    expect(r.total).toBe(2);
    expect(r.onToken).toBe(1);
    expect(r.offToken).toBe(1);
  });
});

describe("rewriteWidths", () => {
  it("maps a value onto a token and preserves the prefix", () => {
    const map = new Map([["lg", "drawer"]]);
    const { out, changed } = rewriteWidths(`<div className="sm:max-w-lg p-base">x</div>`, map);
    expect(changed).toBe(1);
    expect(out).toContain("sm:max-w-drawer");
    expect(out).not.toContain("max-w-lg");
  });

  it("deletes the class when the target is null", () => {
    const map = new Map([["[48%]", null]]);
    const { out, changed } = rewriteWidths(`<div className="flex max-w-[48%] shrink">x</div>`, map);
    expect(changed).toBe(1);
    expect(out).not.toContain("max-w-");
    expect(out).toContain("flex");
    expect(out).toContain("shrink");
  });

  it("leaves a class it has no mapping for alone", () => {
    const map = new Map([["md", "dialog"]]);
    const { out, changed } = rewriteWidths(`<div className="max-w-xl">x</div>`, map);
    expect(changed).toBe(0);
    expect(out).toContain("max-w-xl");
  });

  it("refuses to invent a token that the config does not define", () => {
    // The guard reads its allow-list from tailwind.config.js, so a name that is
    // not there must never be treated as valid.
    expect(TOKENS.has("bogusWidth")).toBe(false);
    expect(TOKENS.has("controlWide")).toBe(true);
  });
});
