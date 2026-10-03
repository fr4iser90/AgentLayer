import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Tailwind 3 → 4 kept most of this app's stylesheet identical, but four utility
 * names silently mean something else, and two preflight rules are gone. Every
 * number in this file was read out of the two builds, not off a changelog:
 *
 *   `shadow-sm`      v3 `0 1px 2px 0 rgba(0,0,0,.05)` → v4 `0 1px 3px 0 …, 0 1px 2px -1px …`
 *                    (v4's `shadow-sm` IS v3's `shadow`; v3's value moved to `shadow-xs`)
 *   `outline-none`   v3 `outline: 2px solid transparent` → v4 `outline-style: none`
 *                    (v4's `outline-hidden` is the v3 rule, including its
 *                    `@media (forced-colors:active)` half — the only focus
 *                    indicator left once a forced-colors theme strips every
 *                    `shadow-focus` ring in the app)
 *   `ring`           3px → 1px (`ring-3` is the v3 width)
 *   `blur`           no v3 equivalent at this name; v4 `blur` = 8px
 *
 * Names that measured identical are deliberately NOT forbidden — `shadow`
 * (`0 1px 3px 0 …`), `rounded` (`.25rem`) and `backdrop-blur` (`blur(8px)`)
 * compile the same in both versions, and a guard that flags them would be
 * scolding call sites for nothing.
 */

const RENAMED = [
  { cls: "shadow-sm", instead: "shadow-xs" },
  { cls: "outline-none", instead: "outline-hidden" },
  { cls: "ring", instead: "ring-3" },
  { cls: "blur", instead: "blur-sm" },
];

const BOUNDARY = (cls: string) => new RegExp(`(?<![\\w-])${cls}(?![\\w-])`);

/** `//` and `/* *​/` prose talks about "the focus ring" without typing the class. */
function stripComments(src: string): string {
  return src.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
}

/**
 * `mascotArt.ts` names an accessory `"ring"`. That is a word in an array, not a
 * class: only a string that carries sibling classes is a class string.
 */
function classStrings(src: string): string[] {
  return [...src.matchAll(/"([^"\\\n]+)"|`([^`\\\n]+)`/g)]
    .map((m) => m[1] ?? m[2] ?? "")
    .filter((s) => s.trim().split(/\s+/).length > 1);
}

function appSources(): { path: string; src: string }[] {
  const out: { path: string; src: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) {
        if (entry.name.includes(".test.")) continue;
        out.push({ path: p, src: stripComments(readFileSync(p, "utf8")) });
      }
    }
  };
  walk(join(process.cwd(), "src"));
  return out;
}

const TREE = appSources();

describe("renamed-away utilities are not typed anywhere", () => {
  for (const { cls, instead } of RENAMED) {
    it(`no call site still uses ${cls} (it would silently mean something else)`, () => {
      const offenders = TREE.flatMap(({ path, src }) =>
        classStrings(src)
          .filter((s) => BOUNDARY(cls).test(s))
          .map((s) => `${path}: "${s.slice(0, 70)}"`)
      );
      expect(offenders, `${cls} → use ${instead}`).toEqual([]);
    });
  }
});

describe("the matcher does not over-match", () => {
  it("ignores a bare word in prose and in a data array", () => {
    expect(classStrings(stripComments(`// the focus ring, and hover state`))).toEqual([]);
    expect(classStrings(`extras: ["ring"], spd: 1.3`)).toEqual([]);
  });

  it("sees the class form of the same word", () => {
    expect(classStrings(`"flex items-center ring hover:bg-white/10"`).some((s) => BOUNDARY("ring").test(s))).toBe(true);
  });

  it("leaves utilities that measured identical alone", () => {
    const s = '"inline-flex rounded shadow backdrop-blur text-ink-primary"';
    for (const cls of ["shadow-sm", "outline-none", "ring", "blur"]) {
      expect(BOUNDARY(cls).test(s), cls).toBe(false);
    }
  });
});

describe("index.css keeps the v4 wiring this project depends on", () => {
  const css = readFileSync(join(process.cwd(), "src/index.css"), "utf8");

  it("turns automatic source detection off, so the guard fixtures cannot ship", () => {
    expect(css).toMatch(/@import\s+"tailwindcss"\s+source\(none\)\s*;/);
    expect(css).toMatch(/@source\s+not\s+"\.\.\/src\/\*\*\/\*\.test\.\{js,ts,jsx,tsx\}"\s*;/);
  });

  it("still reads its theme from the JS config the guards import", () => {
    expect(css).toMatch(/@config\s+"\.\.\/tailwind\.config\.js"\s*;/);
  });

  it("restores the two preflight rules v4 dropped", () => {
    expect(css).toMatch(/button:not\(:disabled\)[\s\S]{0,80}cursor:\s*pointer/);
    expect(css).toMatch(/\[type="search"\][\s\S]{0,80}-webkit-appearance:\s*textfield/);
  });
});
