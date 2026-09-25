import { describe, expect, it } from "vitest";
import { spacingTokens } from "../../scripts/spacing-scan.mjs";

const toks = (src: string) => [...spacingTokens(src)].map(([tok]) => tok);

describe("spacing scanner reads code, not prose", () => {
  it("does not report a class named inside a comment", () => {
    // A JSDoc line explaining what the ramp replaced is byte-for-byte a
    // template literal to a scanner that finds class lists by their quotes.
    // Documenting `py-6` failed a real build over exactly this.
    expect(toks("/** padding used to be `py-6` and `p-8` */\nconst a = \"p-roomy\";")).toEqual([
      "p-roomy",
    ]);
    expect(toks('// the old value was "mb-1"\nconst a = "mt-wide";')).toEqual(["mt-wide"]);
  });

  it("still reports the same class when it is real code", () => {
    // The other half: blanking comments must not become a way to hide drift by
    // wrapping it in something that looks like a comment.
    expect(toks('const a = "mb-1";')).toEqual(["mb-1"]);
    expect(toks("const a = `mb-1`;")).toEqual(["mb-1"]);
  });

  it("does not treat a double slash inside a string as a comment", () => {
    // A URL in an href must not blank the rest of the line and take a real
    // off-ramp class with it.
    expect(toks('const a = "https://example.com";\nconst b = "mb-1";')).toEqual(["mb-1"]);
  });
});

describe("spacing scanner keeps the forms it was built for", () => {
  it("reads direction letters attached directly and dashed gap forms", () => {
    // Tailwind attaches p/m directions directly (`mt-2`) and only dashes
    // gap/space (`gap-x-2`). A pattern describing `m-t` matches nothing real.
    expect(toks('"mt-2 px-4 gap-x-2 space-y-4"')).toEqual(["mt-2", "px-4", "gap-x-2", "space-y-4"]);
  });

  it("recurses into a quoted string inside a template interpolation", () => {
    // Without the nested pass this is a bypass for any off-ramp value.
    expect(toks("className={`flex gap-base ${compact ? \"\" : \"mb-1\"}`}")).toEqual([
      "gap-base",
      "mb-1",
    ]);
  });

  it("reads a variant-prefixed step", () => {
    expect(toks('"hover:mb-13"')).toEqual(["hover:mb-13"]);
  });
});