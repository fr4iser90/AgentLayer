import { describe, expect, it } from "vitest";
import { checkClickOutside, scanClickOutside } from "../../scripts/check-click-outside.mjs";

/**
 * The rule has to catch a copy of the hook without catching everything else
 * that listens on the document, so the tests below are mostly about the edges
 * of "dismissal listener": same event on a window or an element is a different
 * thing, and a keyboard shortcut is not a popover.
 */

const events = (src) => scanClickOutside(src).map((i) => i.event);

describe("scanClickOutside", () => {
  it("flags a dismissal listener copied onto the document", () => {
    expect(events(`document.addEventListener("mousedown", onDoc);`)).toEqual(["mousedown"]);
    expect(events(`document.addEventListener("pointerdown", onPointer);`)).toEqual(["pointerdown"]);
    expect(events(`document.addEventListener("click", onDoc);`)).toEqual(["click"]);
  });

  it("leaves keyboard listeners alone — a shortcut is not a popover", () => {
    expect(events(`document.addEventListener("keydown", onKey);`)).toEqual([]);
    expect(events(`document.addEventListener("visibilitychange", onVis);`)).toEqual([]);
  });

  it("leaves the window alone — drags and tracking live there", () => {
    expect(events(`window.addEventListener("pointermove", onMove);`)).toEqual([]);
    expect(events(`window.addEventListener("mousedown", onDoc);`)).toEqual([]);
  });

  it("leaves an element listener alone", () => {
    expect(events(`panel.addEventListener("pointerdown", onDown);`)).toEqual([]);
  });

  it("survives whitespace between document and the event name", () => {
    expect(events(`document . addEventListener ( 'touchstart' , onDoc );`)).toEqual(["touchstart"]);
  });

  it("reports the line", () => {
    const src = `const a = 1;\nconst b = 2;\ndocument.addEventListener("mousedown", f);`;
    expect(scanClickOutside(src)[0].line).toBe(3);
  });
});

describe("checkClickOutside", () => {
  it("the tree has no popover listening on the document by itself", async () => {
    const r = await checkClickOutside();
    expect(r.findings).toEqual([]);
    expect(r.total).toBe(0);
  });
});