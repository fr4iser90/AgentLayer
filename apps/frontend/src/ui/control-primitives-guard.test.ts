import { readFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  checkControlPrimitive,
  diffBaseline,
  scanControls,
  walk,
} from "../../scripts/check-control-primitive.mjs";
import { attrNames } from "../../scripts/jsx-tags.mjs";
import { stripComments } from "../../scripts/strip-comments.mjs";

/**
 * Two rules, one ledger.
 *
 * The ratchet (bare `<button>` / `<input>` may not grow) is only as honest as
 * the recorded file, so the ledger is tested with invented baselines rather than
 * by rewriting `control-baseline.json` — a test that edits the book it is
 * auditing proves nothing about the book the pre-commit hook reads.
 *
 * The plain-without-block rule has no ledger, so it is tested against the two
 * ways it could silently stop working: a boolean attribute the scanner cannot
 * see (`block` with no `=`, which would flag all 28 converted surfaces forever),
 * and a class name it mistakes for the prop (`className="mt-4 block"`, which
 * would let the drift through).
 */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
// The guard scans source with its comments removed; a test that handed the
// scanner raw source would be measuring a different call than the hook makes.
const kinds = (src, rel = "src/pages/Planted.tsx") =>
  scanControls(rel, stripComments(src)).findings.map((f) => f.kind);
const counts = (src, rel = "src/pages/Planted.tsx") =>
  scanControls(rel, stripComments(src)).counts;

describe("attrNames", () => {
  it("reports a boolean attribute and a value attribute alike", () => {
    expect(attrNames(`<Button variant="plain" block type="button" />`)).toEqual([
      "variant",
      "block",
      "type",
    ]);
  });

  it("does not report a word inside a class list as a prop", () => {
    expect(attrNames(`<Button className="mt-4 block" />`)).toEqual(["className"]);
  });

  it("reads past an expression holding quotes and a >", () => {
    expect(attrNames(`<Button onClick={() => n > 1 && f("a}b")} block />`)).toEqual([
      "onClick",
      "block",
    ]);
  });

  it("marks a spread instead of guessing what is in it", () => {
    expect(attrNames(`<Button {...rest} block />`)).toEqual(["...", "block"]);
  });
});

describe("scanControls — bare controls", () => {
  it("counts a planted <button> and <input>", () => {
    expect(
      counts(`<div><button className="px-2">Los</button><input type="text" value="" /></div>`)
    ).toEqual({ button: 1, input: 1 });
  });

  it("leaves the component and the other tags alone", () => {
    expect(kinds(`<div><Button variant="plain" block>Los</Button><span /></div>`)).toEqual([]);
  });

  it("does not count the types it cannot replace", () => {
    expect(kinds(`<input type="checkbox" checked readOnly />`)).toEqual(["bare-input"]);
    expect(kinds(`<select><option>a</option></select><textarea />`)).toEqual([]);
  });

  it("does not count JSX inside a comment", () => {
    expect(kinds(`// <button className="px-2">alt</button>\n/* <input /> */\n<div />`)).toEqual([]);
  });

  it("sees the bare tags in Button.tsx, so the exemption is what skips them", async () => {
    // If the scanner could not see a hand-rolled button at all, "0 open" would be
    // the answer for every file and the guard would stay green while the app grew.
    const src = await readFile(join(ROOT, "src", "ui", "Button.tsx"), "utf8");
    expect(kinds(src).filter((k) => k === "bare-button").length).toBeGreaterThan(0);
    expect(kinds(src, "src/ui/Button.tsx")).toEqual([]);
  });
});

describe("scanControls — plain without block", () => {
  it("flags a plain button that kept its inline box", () => {
    expect(kinds(`<Button variant="plain" onClick={go}>Datum</Button>`)).toEqual([
      "plain-without-block",
    ]);
    expect(kinds(`<Button variant={"plain"} onClick={go}>Datum</Button>`)).toEqual([
      "plain-without-block",
    ]);
  });

  it("accepts the boolean prop, however it is written", () => {
    expect(kinds(`<Button variant="plain" block onClick={go}>Datum</Button>`)).toEqual([]);
    expect(kinds(`<Button block variant="plain" type="button" />\n`)).toEqual([]);
    expect(kinds(`<Button variant="plain" block\n  onClick={go}\n/>`)).toEqual([]);
  });

  it("is not satisfied by a display class", () => {
    expect(kinds(`<Button variant="plain" className="block w-full">Datum</Button>`)).toEqual([
      "plain-without-block",
    ]);
  });

  it("does not care about the other variants", () => {
    expect(kinds(`<Button variant="primary" onClick={go}>Datum</Button>`)).toEqual([]);
    expect(kinds(`<Button variant="ghost" className="w-full">Datum</Button>`)).toEqual([]);
  });
});

describe("diffBaseline", () => {
  const scanned = new Map([
    ["src/pages/Grew.tsx", { button: 4 }],
    ["src/pages/New.tsx", { input: 2 }],
    ["src/pages/Shrank.tsx", { button: 1 }],
  ]);

  it("reports a file that grew past its recorded number", () => {
    const ledger = {
      "src/pages/Grew.tsx": { button: 3 },
      "src/pages/New.tsx": { input: 2 },
      "src/pages/Shrank.tsx": { button: 1 },
    };
    expect(diffBaseline(ledger, scanned).grew).toEqual([
      { rel: "src/pages/Grew.tsx", tag: "button", n: 4, allowed: 3 },
    ]);
  });

  it("reports every control in a file the ledger does not know", () => {
    // An empty ledger means "nothing hand-painted here yet", which is what makes
    // a new file with one bare button fail instead of sailing through.
    expect(diffBaseline({}, scanned).grew).toEqual([
      { rel: "src/pages/Grew.tsx", tag: "button", n: 4, allowed: 0 },
      { rel: "src/pages/New.tsx", tag: "input", n: 2, allowed: 0 },
      { rel: "src/pages/Shrank.tsx", tag: "button", n: 1, allowed: 0 },
    ]);
  });

  it("reports a recorded number the tree no longer reaches as stale", () => {
    // The ledger is a floor as well as a ceiling: after a conversion pass the
    // entry has to be re-recorded, otherwise the file could grow back into the
    // work already done without anyone noticing.
    const { stale, grew } = diffBaseline(
      {
        "src/pages/Grew.tsx": { button: 4 },
        "src/pages/New.tsx": { input: 2 },
        "src/pages/Shrank.tsx": { button: 5 },
      },
      scanned
    );
    expect(stale).toEqual([{ rel: "src/pages/Shrank.tsx", tag: "button", was: 5, now: 1 }]);
    expect(grew).toEqual([]);
  });

  it("lets a file stay at or below its number", () => {
    const ledger = {
      "src/pages/Grew.tsx": { button: 4 },
      "src/pages/New.tsx": { input: 2 },
      "src/pages/Shrank.tsx": { button: 1 },
    };
    expect(diffBaseline(ledger, scanned).grew).toEqual([]);
  });
});

describe("checkControlPrimitive", () => {
  it("passes the tree with nothing above the ledger", async () => {
    const r = await checkControlPrimitive();
    expect(r.grew).toEqual([]);
    expect(r.plain).toEqual([]);
    expect(r.stale).toEqual([]);
  });

  it("still counts what it counts — the ledger describes the tree it audits", async () => {
    const r = await checkControlPrimitive();
    const files = [];
    for await (const file of walk(join(ROOT, "src"))) files.push(file);
    let button = 0;
    let input = 0;
    for (const file of files) {
      const rel = relative(ROOT, file).split("\\").join("/");
      const c = counts(await readFile(file, "utf8"), rel);
      button += c.button ?? 0;
      input += c.input ?? 0;
    }
    expect(r.totals.button).toBe(button);
    expect(r.totals.input).toBe(input);
    // The goal for this batch: 370 -> under 100 buttons, 294 -> under 150 inputs.
    expect(button).toBeLessThan(100);
    expect(input).toBeLessThan(150);
  });
});