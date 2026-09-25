import { describe, expect, it } from "vitest";
import {
  INTENTIONAL,
  bareClassName,
  intentionalKeys,
  intentionalReason,
  unhitIntentionalKeys,
} from "../../scripts/intentional-colours.mjs";

/**
 * The allow-list is the record that says "this raw colour is not debt", which
 * makes it the record most worth corrupting: a baseline that grows is annoying,
 * an allow-list that grows quietly ends the migration. Everything here is about
 * keeping it unable to do that.
 */

describe("a justification is keyed by colour, not by state", () => {
  it("drops the variant chain before looking up", () => {
    expect(bareClassName("group-hover:border-sky-500/45")).toBe("border-sky-500/45");
    expect(bareClassName("border-line")).toBe("border-line");
    expect(
      intentionalReason("src/features/chat/AgentActivityPanel.tsx", "data-[state=open]:border-sky-500/45")
    ).toBeTruthy();
  });

  it("never covers a hue that was not listed", () => {
    // The planted violation: if the lookup were a prefix or hue match, listing
    // `border-sky-500/45` would also permit `border-sky-600/45`, and the list
    // would stop being a list of decisions.
    expect(
      intentionalReason("src/features/chat/AgentActivityPanel.tsx", "border-sky-600/45")
    ).toBeUndefined();
    expect(
      intentionalReason("src/features/chat/AgentActivityPanel.tsx", "border-sky-500/46")
    ).toBeUndefined();
  });

  it("is scoped to the file that made the decision", () => {
    // `border-orange-500/50` is justified on the dashboard canvas as a third
    // block state. In any other file it is an unexplained raw hue.
    expect(
      intentionalReason("src/features/dashboard/DashboardGridInner.tsx", "border-orange-500/50")
    ).toBeTruthy();
    expect(
      intentionalReason("src/features/dashboard/DashboardPage.tsx", "border-orange-500/50")
    ).toBeUndefined();
  });
});

describe("each guard only counts its own property", () => {
  const borderKeys = intentionalKeys((cls) => cls.startsWith("border-"));
  const bgKeys = intentionalKeys((cls) => cls.startsWith("bg-"));

  it("a fill can never be a hit for the border guard", () => {
    const fillsOnly = new Set(bgKeys);
    expect(unhitIntentionalKeys(fillsOnly, (cls) => cls.startsWith("bg-"))).toEqual([]);
    // Same hits, different scope: every border exception is still open. Without
    // the split, a justified chip fill would silently excuse a raw hairline in
    // the same file that happens to share its hue.
    expect(unhitIntentionalKeys(fillsOnly, (cls) => cls.startsWith("border-")).length).toBe(
      borderKeys.length
    );
    expect(borderKeys.length).toBeGreaterThan(0);
  });

  it("an empty hit set reports every listed key of the scope", () => {
    expect(unhitIntentionalKeys(new Set(), (cls) => cls.startsWith("border-")).length).toBe(
      borderKeys.length
    );
  });

  it("a justification whose class left the tree is reported", () => {
    // The reason the guards fail on this rather than ignore it: a reader who
    // sees a reasoned entry assumes the reasoning was checked today.
    const [first] = borderKeys;
    const hit = new Set(borderKeys.filter((k) => k !== first));
    expect(unhitIntentionalKeys(hit, (cls) => cls.startsWith("border-"))).toEqual([first]);
  });
});

describe("every listed exception is a sentence, not a flag", () => {
  it("has a reason for every class it lists", () => {
    const empty = Object.entries(INTENTIONAL).flatMap(([file, byClass]) =>
      Object.entries(byClass)
        .filter(([, reason]) => typeof reason !== "string" || reason.trim().length < 20)
        .map(([cls, reason]) => `${file}::${cls} (${JSON.stringify(reason)})`)
    );
    expect(empty).toEqual([]);
  });

  it("lists no file twice and no class twice", () => {
    const keys = intentionalKeys();
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("justifies a catalogue as a whole, not one row of it", () => {
    // A capability chip has border, fill and label; justifying two of the three
    // leaves the third in the baseline, where it reads as unfinished work and
    // gets "migrated" by the next pass — splitting one visual decision in two.
    const chip = INTENTIONAL["src/features/chat/ModelCatalogSelect.tsx"];
    for (const hue of ["sky", "violet", "amber", "emerald"]) {
      const props = Object.keys(chip)
        .filter((cls) => cls.includes(`-${hue}-`))
        .map((cls) => cls.split("-")[0]);
      expect(new Set(props), hue).toEqual(new Set(["border", "bg", "text"]));
    }
  });
});