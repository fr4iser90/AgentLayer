import { describe, expect, it } from "vitest";
import { scanSilentCatches } from "../../scripts/check-silent-catch.mjs";

const lines = (src: string) => scanSilentCatches(src).map((f) => f.line);

/**
 * The rule is not "never swallow", it is "never swallow without saying what you
 * gave up". So the test that matters most here is the one where a `// why:`
 * line makes the guard stand down — the first version read the reason out of the
 * comment-stripped copy, found nothing, and rejected every annotated site, i.e.
 * shipped a rule nobody could satisfy.
 */
describe("silent-catch guard reads the reason", () => {
  it("flags a swallow with no reason", () => {
    expect(lines('await save().catch(() => {});')).toEqual([1]);
    expect(lines('await save().catch(() => undefined);')).toEqual([1]);
    expect(lines('await save().catch(() => null);')).toEqual([1]);
    expect(lines('await save().catch(() => noop);')).toEqual([1]);
  });

  it("accepts a reason on the line above", () => {
    expect(
      lines('// why: a lost ping must not surface.\nawait save().catch(() => {});')
    ).toEqual([]);
  });

  it("accepts a reason on the same line", () => {
    expect(lines('await save().catch(() => {}); // why: fire-and-forget telemetry')).toEqual([]);
  });

  it("reports the line the reader would look at", () => {
    const src = ['const a = 1;', 'const b = 2;', 'await save().catch(() => {});'].join("\n");
    expect(lines(src)).toEqual([3]);
  });
});

describe("silent-catch guard does not invent or lose work", () => {
  it("does not see a swallow that only appears in a comment", () => {
    // The guard scans whole files. Its own documentation names the pattern it
    // forbids, and without comment blanking that mention would be a violation.
    expect(lines('/** This file forbids `.catch(() => {})`. */\nexport const x = 1;')).toEqual([]);
    expect(lines('// do not write .catch(() => null) here\nexport const x = 1;')).toEqual([]);
  });

  it("accepts a real handler", () => {
    expect(lines("await save().catch(report);")).toEqual([]);
    expect(lines("await save().catch((e) => console.error(e));")).toEqual([]);
  });

  it("counts every swallow in a file", () => {
    const src = ['a().catch(() => {});', 'b().catch(() => null);', 'c().catch(report);'].join(
      "\n"
    );
    expect(lines(src)).toEqual([1, 2]);
  });

  it("reads a swallow whose arrow takes a typed parameter", () => {
    expect(lines('save().catch((_: unknown) => {});')).toEqual([1]);
  });
});