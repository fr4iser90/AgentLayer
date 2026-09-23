/**
 * Shared scanner for Tailwind spacing utilities.
 *
 * Both the codemod and the guard need to find the same set of tokens, so the
 * scanning lives here once. Two things make this more than a regex over
 * className strings:
 *
 * 1. Tailwind attaches direction letters DIRECTLY to padding/margin
 *    (`mt-2`, `px-4`) and only uses a dash for gap/space (`gap-x-2`,
 *    `space-y-4`). A pattern like `(?:p|m)(?:-[xytrbl])?` describes `m-t`
 *    and matches nothing real. An earlier version of the codemod had exactly
 *    that and reported 1133 classes for a dimension of 5248 — masked because
 *    the dashed gap/space forms did work.
 *
 * 2. A class can hide inside a nested quoted string within a template
 *    interpolation, as in
 *
 *      className={`flex gap-base ${compact ? "" : "mb-1"}`}
 *
 *    The outer scan consumes the whole template as one class string, so the
 *    whitespace split yields `"mb-1"}` — quoted, unmatched. Without the
 *    nested pass below, that class is invisible to the guard too, which
 *    makes the interpolation an easy bypass for any off-ramp value.
 */

// Longest-first so `px` is never shadowed by `p`.
export const UTIL =
  "(?:space-x|space-y|gap-x|gap-y|px|py|pt|pr|pb|pl|mx|my|mt|mr|mb|ml|p|m|gap)";

// Double/single-quoted strings nested inside a template interpolation.
const NESTED_QUOTES = /"([^"\n]*)"|'([^'\n]*)'/g;

// A Tailwind spacing step: a number, the built-in `px`, `auto`, or one of
// the ramp names. Deliberately narrow — an open `.+` here also matched
// unrelated template literals whose first segment happened to start with a
// utility letter, e.g. the storage key `m-${Date.now()}-${Math.random()…}`,
// which the guard then baselined as if it were a spacing class.
const STEP =
  "(?:[0-9]+(?:\\.[0-9]+)?|px|auto|hair|tight|snug|base|firm|soft|wide|roomy|broad|deep|page|grand)";

// A spacing utility with any real step value. STEP must stay wrapped in a
// capturing group: it is non-capturing itself, so without the outer parens
// there is no group 2 at all, `hit[2]` is undefined for every token, and
// the guard then classifies nothing as on-ramp — which, right after an
// --update, means it baselines the entire ramp and still exits 0.
const ANY_SPACING = new RegExp(
  "^((?:[a-zA-Z0-9-]+:)*-?" + UTIL + ")-(" + STEP + ")$"
);

// The named ramp, mirroring tailwind.config.js.
export const NAMED = new Set([
  "hair",
  "tight",
  "snug",
  "base",
  "firm",
  "soft",
  "wide",
  "roomy",
  "broad",
  "deep",
  "page",
  "grand",
]);

// Values that are not ramp positions but are legitimate as-is.
export const ZERO = "0"; // "explicitly zero" is a statement
export const PX = "px"; // Tailwind's built-in 1px, used for hairline insets
export const AUTO = "auto";

/**
 * Yield every whitespace-separated token in a class-string body, recursing
 * into quoted strings nested inside `${...}` interpolations.
 */
function* tokensIn(body, depth = 0) {
  for (const tok of body.split(/\s+/)) {
    if (tok !== "") yield tok;
  }
  if (depth < 6 && body.includes("${")) {
    for (const m of body.matchAll(NESTED_QUOTES)) {
      const inner = m[1] ?? m[2] ?? "";
      if (inner.trim() !== "") yield* tokensIn(inner, depth + 1);
    }
  }
}

/**
 * Yield [token, value] for every spacing utility found in a source file.
 * `value` is the Tailwind step: a number, "px", "auto", or a ramp name.
 */
export function* spacingTokens(src) {
  const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;
  for (const m of src.matchAll(CLASS_STRINGS)) {
    const body = m[1] ?? m[2] ?? m[3] ?? "";
    if (body === "") continue;
    for (const tok of tokensIn(body)) {
      const hit = tok.match(ANY_SPACING);
      if (hit) yield [tok, hit[2]];
    }
  }
}

/**
 * Rewrite one class-string body onto the named ramp. Returns the new body and
 * how many tokens were mapped. Mirrors the nesting recursion of tokensIn so
 * what is counted is what gets rewritten.
 */
function mapBody(body, map, depth = 0) {
  let changed = 0;
  const out = body
    .split(/(\s+)/)
    .map((part) => {
      if (/^\s+$/.test(part) || part === "") return part;
      const hit = part.match(ANY_SPACING);
      if (!hit) return part;
      const named = map.get(hit[2]);
      if (named === undefined) return part;
      changed += 1;
      return `${hit[1]}-${named}`;
    })
    .join("");
  if (depth < 6 && out.includes("${")) {
    const nested = out.replace(NESTED_QUOTES, (mm, dq, sq) => {
      const inner = dq ?? sq ?? "";
      if (inner.trim() === "") return mm;
      const r = mapBody(inner, map, depth + 1);
      changed += r.changed;
      const q = dq !== undefined && dq !== null ? '"' : "'";
      return q + r.out + q;
    });
    return { out: nested, changed };
  }
  return { out, changed };
}

/**
 * Rewrite a whole source file. `map` is numeric Tailwind step -> ramp name.
 * Returns the new source plus per-token counts of what was mapped.
 */
export function rewriteSpacing(src, map) {
  const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;
  const counts = new Map();
  let changed = 0;
  const out = src.replace(CLASS_STRINGS, (match, dq, bt, sq) => {
    const body = dq ?? bt ?? sq ?? "";
    if (body === "") return match;
    // Count before rewriting, from the same token stream the rewrite uses.
    for (const tok of tokensIn(body)) {
      const hit = tok.match(ANY_SPACING);
      if (hit && map.has(hit[2])) counts.set(tok, (counts.get(tok) ?? 0) + 1);
    }
    const r = mapBody(body, map);
    if (!r.changed) return match;
    changed += r.changed;
    const quote =
      dq !== undefined && dq !== null ? '"' : bt !== undefined && bt !== null ? "`" : "'";
    return quote + r.out + quote;
  });
  return { out, changed, counts };
}
