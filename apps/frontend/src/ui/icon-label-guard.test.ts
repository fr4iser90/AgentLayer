import { describe, expect, it } from "vitest";
import { scanSource } from "../../scripts/check-icon-label.mjs";

const ICONS = new Set(["Play", "Pause", "X", "Trash2"]);

const scan = (src: string) => scanSource(src, "Test.tsx", ICONS);

describe("icon-label guard", () => {
  it("marks an icon-only button with no accessible name as a violation", () => {
    const r = scan(`<button onClick={go}><Play /></button>`);
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(1);
  });

  it("accepts aria-label", () => {
    const r = scan(`<button aria-label="Start" onClick={go}><Play /></button>`);
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(0);
    expect(r.named[0].how).toBe("aria-label");
  });

  it("accepts aria-labelledby", () => {
    const r = scan(`<button aria-labelledby="lbl-1"><Play /></button>`);
    expect(r.violations).toHaveLength(0);
    expect(r.named[0].how).toBe("aria-labelledby");
  });

  it("accepts a wrapping Tooltip", () => {
    const r = scan(
      `<Tooltip label="Start"><button onClick={go}><Play /></button></Tooltip>`,
    );
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(0);
    expect(r.named[0].how).toBe("Tooltip label");
  });

  it("does not accept an empty aria-label", () => {
    // aria-label="" hides an element from assistive tech rather than naming it.
    const r = scan(`<button aria-label="" onClick={go}><Play /></button>`);
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(1);
  });

  it("does not accept a lookalike attribute such as xtitle", () => {
    const r = scan(`<button xtitle="Start"><Play /></button>`);
    expect(r.violations).toHaveLength(1);
  });

  it("leaves a button with visible text alone", () => {
    const r = scan(`<button onClick={go}>Start</button>`);
    expect(r.iconOnly).toBe(0);
    expect(r.violations).toHaveLength(0);
  });

  it("leaves an icon-plus-text button alone", () => {
    const r = scan(`<button onClick={go}><Play /> Start</button>`);
    expect(r.iconOnly).toBe(0);
    expect(r.violations).toHaveLength(0);
  });

  it("does not treat a non-icon child component as an icon", () => {
    const r = scan(`<button onClick={go}><Spinner /></button>`);
    expect(r.iconOnly).toBe(0);
  });

  it("counts a raw svg as an icon", () => {
    const r = scan(`<button onClick={go}><svg viewBox="0 0 8 8" /></button>`);
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(1);
  });

  it("does not confuse <buttonbar> with <button>", () => {
    const r = scan(`<buttonbar><Play /></buttonbar>`);
    expect(r.buttons).toBe(0);
  });

  it("does not count a Tooltip that closed earlier as an ancestor", () => {
    const r = scan(
      `<Tooltip label="anders"><span>x</span></Tooltip><button><Play /></button>`,
    );
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(1);
  });

  it("sees a Tooltip ancestor across multiple lines", () => {
    const src = [
      "<Tooltip label={t('x')}>",
      "  <button",
      "    onClick={go}",
      "  >",
      "    <Play />",
      "  </button>",
      "</Tooltip>",
    ].join("\n");
    const r = scan(src);
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(0);
    expect(r.named[0].how).toBe("Tooltip label");
  });

  it("counts every button in a file and reports each violation separately", () => {
    const src = [
      "<div>",
      '  <button aria-label="ok"><Play /></button>',
      "  <button><Pause /></button>",
      "  <button><X /></button>",
      "</div>",
    ].join("\n");
    const r = scan(src);
    expect(r.buttons).toBe(3);
    expect(r.iconOnly).toBe(3);
    expect(r.named).toHaveLength(1);
    expect(r.violations).toHaveLength(2);
  });

  it("is not fooled by a > inside an attribute expression", () => {
    // The `>` in `a > b` is not the end of the tag. A scanner that stopped there
    // would see no children at all and call the button empty rather than named.
    const r = scan(
      `<button aria-label="Start" disabled={a > b}><Play /></button>`,
    );
    expect(r.iconOnly).toBe(1);
    expect(r.violations).toHaveLength(0);
  });
});
