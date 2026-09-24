import { describe, expect, it } from "vitest";
import { scanFills } from "../../scripts/check-fill-token.mjs";

const hues = (src: string) => scanFills(src).map((f) => f.cls);
const count = (src: string) => scanFills(src).length;

describe("fill guard sees the palette", () => {
  it("flags a plain palette fill", () => {
    expect(count(`"bg-red-500"`)).toBe(1);
    expect(hues(`"bg-red-500"`)).toEqual(["bg-red-500"]);
  });

  it("admits the opacity modifier", () => {
    // Without `/` in the value class, `bg-red-500/50` fails the boundary check
    // at the slash and becomes invisible — the exact defect that made the ink
    // guard report 314 raw text colours while 563 were in the tree.
    expect(count(`"bg-red-500/50"`)).toBe(1);
    expect(count(`"bg-sky-950/40"`)).toBe(1);
  });

  it("admits the variant-prefix chain", () => {
    // Anchoring on whitespace alone left 206 prefixed palette classes unseen.
    expect(count(`"hover:bg-sky-600/25"`)).toBe(1);
    expect(count(`"sm:focus:bg-amber-500/20"`)).toBe(1);
    expect(count(`"group-hover:bg-emerald-900/40"`)).toBe(1);
  });

  it("counts several fills in one class string", () => {
    expect(count(`"bg-sky-950/40 hover:bg-sky-900/40 bg-amber-600/25"`)).toBe(3);
  });

  it("catches the chip recipe the Badge primitive exists to replace", () => {
    expect(
      count(`"rounded-pill border border-violet-500/30 bg-violet-600/20 px-base py-hair text-meta text-violet-200"`)
    ).toBe(1);
  });
});

describe("compliant fills are invisible", () => {
  it("does not flag semantic tokens from tailwind.config.js", () => {
    expect(count(`"bg-danger-subtle bg-accent-subtle bg-success-subtle"`)).toBe(0);
    expect(count(`"bg-card bg-field bg-canvas bg-panel"`)).toBe(0);
  });

  it("does not flag scrims and veils", () => {
    expect(count(`"bg-black/60 bg-white/10 bg-white/[0.04]"`)).toBe(0);
  });

  it("does not flag gradient stops (they are from-/to-, not bg-)", () => {
    expect(count(`"from-slate-900/90 to-black/60"`)).toBe(0);
  });
});

describe("matcher must not over-match", () => {
  it("does not match a shade-less or one-digit hue", () => {
    expect(count(`"bg-sky bg-red-1"`)).toBe(0);
  });

  it("does not match a longer token that merely starts with a hue", () => {
    expect(count(`"bg-red-5000"`)).toBe(0);
    expect(count(`"bg-reddish-500"`)).toBe(0);
  });

  it("does not match bg-text-* or a hue in another property", () => {
    expect(count(`"text-red-500 border-red-500"`)).toBe(0);
  });

  it("does not match a hue name that is not in the palette", () => {
    expect(count(`"bg-banana-500"`)).toBe(0);
  });
});

describe("both lists come from their real source, not a copy", () => {
  it("palette hues resolve from tailwindcss/colors.js", async () => {
    const colors = (await import("tailwindcss/colors.js")).default;
    for (const h of ["sky", "emerald", "amber", "red", "rose", "violet", "indigo", "orange"]) {
      expect(colors).toHaveProperty(h);
      expect(count(`"bg-${h}-600"`)).toBe(1);
    }
  });

  it("semantic names resolve from tailwind.config.js", async () => {
    const config = (await import("../../tailwind.config.js")).default;
    for (const t of ["accent", "success", "warning", "danger", "badge", "ink"]) {
      expect(config.theme.extend.colors).toHaveProperty(t);
    }
    expect(count(`"bg-accent-subtle"`)).toBe(0);
  });
});
