import { readFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  checkPrimitiveCoverage,
  countConsumers,
  findOrphans,
  resolveSpecifier,
  scanSpecifiers,
  walk,
} from "../../scripts/check-primitive-coverage.mjs";

/**
 * The guard's promise is a fact about the tree — "every primitive is used" — so
 * the test has to be a fact about the scanner's eyes as well. Everything here
 * runs through the same functions the pre-commit hook calls, with one planted
 * module added to the real scan: if `findOrphans` cannot see a `src/ui/` file
 * that demonstrably has no importer, the green run in the other test would mean
 * nothing.
 */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

async function scanRealTree() {
  const files = [];
  for await (const file of walk(join(ROOT, "src"))) {
    const src = await readFile(file, "utf8");
    files.push({
      rel: relative(ROOT, file).split("\\").join("/"),
      specifiers: scanSpecifiers(src),
    });
  }
  return files;
}

describe("scanSpecifiers", () => {
  it("reads relative imports and dynamic imports", () => {
    expect(
      scanSpecifiers(`import { A } from "./A";\nconst B = () => import("../ui/Button");`)
    ).toEqual(["./A", "../ui/Button"]);
  });

  it("ignores a specifier inside a comment", () => {
    expect(scanSpecifiers(`// from "../ui/Ghost"\n/* import("./AlsoGhost") */`)).toEqual([]);
  });

  it("ignores package imports — they cannot point at src/ui", () => {
    expect(scanSpecifiers(`import { useState } from "react";`)).toEqual([]);
  });
});

describe("resolveSpecifier", () => {
  it("lands a sibling and a parent-relative import on the same module", () => {
    const fromUi = resolveSpecifier("src/ui/Menu.tsx", "./Tabs");
    const fromPage = resolveSpecifier("src/pages/X.tsx", "../ui/Tabs");
    expect(fromUi).toBe("src/ui/Tabs");
    expect(fromPage).toBe(fromUi);
  });

  it("returns null for a specifier leaving src/", () => {
    expect(resolveSpecifier("src/pages/X.tsx", "../../../package.json")).toBeNull();
  });
});

describe("findOrphans", () => {
  it("flags a planted ui module that nothing imports", () => {
    const orphans = findOrphans([
      { rel: "src/ui/Planted.tsx", specifiers: [] },
      { rel: "src/pages/Home.tsx", specifiers: ["../ui/Used"] },
      { rel: "src/ui/Used.tsx", specifiers: [] },
    ]);
    expect(orphans.map((o) => o.module)).toEqual(["src/ui/Planted.tsx"]);
  });

  it("accepts an importer from inside src/ui, but still wants one for itself", () => {
    // Table.tsx loading Skeleton.tsx satisfies the rule for Skeleton — what the
    // guard refuses is a module no other file loads. Table is itself unreferenced
    // here, so it is the one left on the list.
    const files = [
      { rel: "src/ui/Planted.tsx", specifiers: [] },
      { rel: "src/ui/Table.tsx", specifiers: ["./Planted"] },
    ];
    expect(findOrphans(files).map((o) => o.module)).toEqual(["src/ui/Table.tsx"]);
    expect(countConsumers(files)).toEqual([
      { module: "src/ui/Planted.tsx", outside: 0, inside: 1 },
      { module: "src/ui/Table.tsx", outside: 0, inside: 0 },
    ]);
  });

  it("does not let a module import itself into being used", () => {
    expect(
      findOrphans([{ rel: "src/ui/Planted.tsx", specifiers: ["./Planted"] }])
    ).toEqual([{ module: "src/ui/Planted.tsx", fromUi: [], fromApp: [] }]);
  });

  it("only looks at .tsx in the ui folder", () => {
    expect(findOrphans([{ rel: "src/ui/notes.ts", specifiers: [] }])).toEqual([]);
  });
});

describe("checkPrimitiveCoverage", () => {
  it("passes the tree with nothing orphaned", async () => {
    const r = await checkPrimitiveCoverage();
    expect(r.orphans).toEqual([]);
    expect(r.covered).toBeGreaterThanOrEqual(20);
  });

  it("still sees an orphan once the real tree is scanned", async () => {
    // Same input the run above produces, plus one invented file. Without this,
    // an exemption or a path bug wide enough to hide the orphan in the run would
    // also hide every primitive that never got wired up.
    const files = await scanRealTree();
    const withPlanted = [...files, { rel: "src/ui/PlantedOrphan.tsx", specifiers: [] }];
    const orphans = findOrphans(withPlanted);
    expect(orphans.map((o) => o.module)).toEqual(["src/ui/PlantedOrphan.tsx"]);

    // And the planted module stops being an orphan as soon as a surface loads it.
    const wired = [...withPlanted, { rel: "src/pages/Planted.tsx", specifiers: ["../ui/PlantedOrphan"] }];
    expect(findOrphans(wired)).toEqual([]);
  });
});