import { describe, expect, it } from "vitest";
import { fixLabelOnFill, mapClass } from "../../scripts/codemod-status-hues.mjs";

/**
 * The four status hues are the one part of the palette where the mapping is
 * mechanical — red→danger, amber→warning, emerald→success, sky→accent — and the
 * mechanism is the level of the raw class. These tests pin that mechanism,
 * because a wrong level rule does not fail loudly: it produces a token that
 * renders and reads fine on the surface it was written for, and fails
 * contrast on the one it lands on later.
 *
 * The negative cases are the load-bearing ones. `mapClass` returning `null`
 * means "leave this alone", so a rule that stops returning null silently
 * rewrites things that were already correct — including the tokens this
 * migration produces, which is how a codemod eats its own output.
 */

const mapped = (cls: string) => mapClass(cls, []);

describe("status hues map by level", () => {
  it("turns a tinted fill into the subtle token and drops the alpha", () => {
    expect(mapped("bg-amber-950/20")).toBe("bg-warning-subtle");
    expect(mapped("bg-red-50")).toBe("bg-danger-subtle");
    expect(mapped("hover:bg-sky-900/40")).toBe("hover:bg-accent-subtle");
  });

  it("keeps a solid fill solid, and gives an interaction state the hover token", () => {
    expect(mapped("bg-emerald-600")).toBe("bg-success");
    expect(mapped("hover:bg-red-500")).toBe("hover:bg-danger-hover");
    expect(mapped("focus:bg-amber-500")).toBe("focus:bg-warning-hover");
    // A state that is not a pointer state — the element is expanded, not
    // hovered — has no hover tone to move to, so it keeps the DEFAULT. The
    // hover rule is about the pointer, not about any boolean.
    expect(mapped("dark:bg-sky-500")).toBe("dark:bg-accent");
  });

  it("sends a bright label to the badge step and a mid label to the regular one", () => {
    // The break sits between 300 and 400 because that is where the raw palette
    // crosses the badge/text contrast boundary on a dark surface.
    expect(mapped("text-sky-200")).toBe("text-badge-accent");
    expect(mapped("text-emerald-300/90")).toBe("text-badge-success");
    expect(mapped("text-amber-400")).toBe("text-warning");
    expect(mapped("text-red-500/50")).toBe("text-danger");
  });

  it("moves a hovered label to the hover token", () => {
    expect(mapped("hover:text-amber-500")).toBe("hover:text-warning-hover");
    // A bright label already has its hover pair in the badge step: hover must
    // not darken it, which is what the regular token's hover would do.
    expect(mapped("hover:text-sky-200")).toBe("hover:text-badge-accent");
  });

  it("keeps the alpha on a hairline and the stop on a gradient", () => {
    // Hairline alpha carries weight, hue carries meaning; the level is only a
    // starting point. A gradient stop loses its ramp position, because a token
    // has no levels — `from-sky-400` cannot become `from-accent-400`, that class
    // does not exist and would compile to nothing.
    expect(mapped("border-sky-500/35")).toBe("border-accent/35");
    expect(mapped("divide-amber-500/20")).toBe("divide-warning/20");
    expect(mapped("ring-red-500/40")).toBe("ring-danger/40");
    expect(mapped("from-sky-400")).toBe("from-accent");
    expect(mapped("to-amber-600")).toBe("to-warning");
  });
});

describe("status hues leave alone what is not a raw status hue", () => {
  it("does not touch a token this migration already produced", () => {
    // The planted violation: if these returned a value, re-running the codemod
    // would walk its own output — `bg-warning-subtle` → `bg-warning-subtle`
    // looks harmless until the rule layer changes and it quietly moves twice.
    expect(mapped("bg-warning-subtle")).toBeNull();
    expect(mapped("text-badge-danger")).toBeNull();
    expect(mapped("border-line-strong")).toBeNull();
  });

  it("does not touch a raw class of a hue outside the four", () => {
    expect(mapped("bg-orange-500/10")).toBeNull();
    expect(mapped("text-violet-300")).toBeNull();
    expect(mapped("border-teal-500/45")).toBeNull();
  });

  it("does not touch a class that merely contains a hue name", () => {
    expect(mapped("bg-sky")).toBeNull();
    expect(mapped("text-skyline-500")).toBeNull();
  });
});

describe("a status label on a status fill", () => {
  it("brightens a label sitting on its own tint", () => {
    // 4.3:1 — both halves are correct tokens, which is exactly why no token
    // guard sees the pair. The level rules cannot see it either: `text-warning`
    // is a legal label in isolation and an unreadable one here.
    expect(fixLabelOnFill('"text-warning bg-warning-subtle"')).toBe('"text-badge-warning bg-warning-subtle"');
    expect(fixLabelOnFill('"bg-danger-subtle text-danger"')).toBe('"bg-danger-subtle text-badge-danger"');
  });

  it("darkens a label sitting on a solid fill instead", () => {
    expect(fixLabelOnFill('"bg-danger text-danger"')).toBe('"bg-danger text-ink-on-fill"');
  });

  it("leaves a label whose fill is a different hue, or no fill at all", () => {
    expect(fixLabelOnFill('"bg-warning-subtle text-danger"')).toBe('"bg-warning-subtle text-danger"');
    expect(fixLabelOnFill('"text-danger"')).toBe('"text-danger"');
    expect(fixLabelOnFill('"bg-accent-subtle text-badge-accent"')).toBe('"bg-accent-subtle text-badge-accent"');
  });

  it("keeps a variant prefix while retargeting the label", () => {
    expect(fixLabelOnFill('"bg-warning-subtle hover:text-warning"')).toBe('"bg-warning-subtle hover:text-badge-warning"');
  });
});