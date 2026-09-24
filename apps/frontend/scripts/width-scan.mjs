/**
 * Shared scanner for Tailwind content-width utilities.
 *
 * Same shape as spacing-scan.mjs, for the reasons documented there: the codemod
 * and the guard must agree on what a token is, so the scanning lives here once.
 * Two properties that a naive `className` regex does not have:
 *
 * 1. A class can hide inside a nested quoted string within a template
 *    interpolation (`${wide ? "max-w-md" : ""}`). The outer scan consumes the
 *    whole template as one class string, so without the nested pass the class is
 *    invisible to the guard as well — which makes the interpolation a bypass.
 *
 * 2. Responsive and state prefixes are real (`sm:max-w-lg`, `hover:max-w-full`).
 *    The prefix is carried through so a prefixed class is still inspected rather
 *    than skipped.
 *
 * The allowed token names are READ FROM tailwind.config.js rather than repeated
 * here. The spacing guard keeps its own copy of the ramp, so renaming a token in
 * the config leaves that guard green while the classes it checks no longer
 * exist. Reading the config makes that impossible: rename a token and every call
 * site of the old name becomes a violation on the next run.
 */
import config from "../tailwind.config.js";

export const TOKENS = new Set(Object.keys(config.theme.extend.maxWidth));

// `max-w-` with any prefix chain, then either an arbitrary bracketed value or a
// bare scale name. The value admits BOTH things that actually occur and that a
// narrower class silently drops:
//
//   - a leading digit — Tailwind's scale is `2xl`/`3xl`/`4xl`/`5xl`/`6xl` and
//     `max-w-64`, so an alpha-first value drops 57 of 183 call sites
//   - an interior capital — the ramp is camelCase (`controlWide`, `pageNarrow`),
//     so a lowercase-only value fails to see every token this migration writes,
//     which makes the guard report a shrinking population and go green while
//     counting nothing it just created
//
// Deliberately will not match `min-w-` or `max-h-`.
const ANY_WIDTH =
  /^((?:[a-zA-Z0-9-]+:)*max-w)-(\[[^\]]*\]|[a-z0-9][a-zA-Z0-9-]*)$/;

// Double/single-quoted strings nested inside a template interpolation.
const NESTED_QUOTES = /"([^"\n]*)"|'([^'\n]*)'/g;

/**
 * Yield every whitespace-separated token in a class-string body, recursing into
 * quoted strings nested inside `${...}` interpolations.
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

/** True when the scale value is one of the config's maxWidth tokens. */
export function isToken(value) {
  return TOKENS.has(value);
}

/**
 * Yield [token, value] for every `max-w-*` utility found in a source string.
 * `value` is the bare scale name or the bracketed arbitrary value.
 */
export function* widthTokens(src) {
  const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;
  for (const m of src.matchAll(CLASS_STRINGS)) {
    const body = m[1] ?? m[2] ?? m[3] ?? "";
    if (body === "") continue;
    for (const tok of tokensIn(body)) {
      const hit = tok.match(ANY_WIDTH);
      if (hit) yield [tok, hit[2]];
    }
  }
}

/**
 * Rewrite one class-string body. `map` maps an old scale value to a new token
 * name. Mirrors the nesting recursion of tokensIn so what is counted is what
 * gets rewritten.
 */
function mapBody(body, map, depth = 0) {
  let changed = 0;
  const out = body
    .split(/(\s+)/)
    .map((part) => {
      if (/^\s+$/.test(part) || part === "") return part;
      const hit = part.match(ANY_WIDTH);
      if (!hit) return part;
      const named = map.get(hit[2]);
      if (named === undefined) return part;
      changed += 1;
      return named === null ? "" : `${hit[1]}-${named}`;
    })
    .join("")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
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
 * Rewrite a whole source file. `map` is old scale value -> new token name, or
 * null to delete the class outright. Returns the new source plus per-value
 * counts of what was mapped.
 */
export function rewriteWidths(src, map) {
  const CLASS_STRINGS = /"([^"\n]*)"|`([\s\S]*?)`|'([^'\n]*)'/g;
  const counts = new Map();
  let changed = 0;
  const out = src.replace(CLASS_STRINGS, (match, dq, bt, sq) => {
    const body = dq ?? bt ?? sq ?? "";
    if (body === "") return match;
    for (const tok of widthTokens(body)) {
      if (map.has(tok[1])) counts.set(tok[1], (counts.get(tok[1]) ?? 0) + 1);
    }
    const r = mapBody(body, map);
    if (!r.changed) return match;
    changed += r.changed;
    const quote =
      dq !== undefined && dq !== null
        ? '"'
        : bt !== undefined && bt !== null
          ? "`"
          : "'";
    return quote + r.out + quote;
  });
  return { out, changed, counts };
}
