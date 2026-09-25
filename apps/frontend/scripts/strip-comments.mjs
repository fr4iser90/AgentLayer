/**
 * Blank out comments while preserving every character offset and newline, so
 * line numbers stay correct after stripping.
 *
 * Shared because three guards need the identical behaviour and a second
 * implementation is how one gets fixed while the other stays blind:
 *
 * - `check-ink-color.mjs` scans whole files rather than only JSX tags, so a
 *   class string in a module-level constant is visible to it. Comments are the
 *   one place a widened scan picks up things that are not code — this repo's
 *   own guard docs name `text-slate-300` as an example, and would report it.
 * - `spacing-scan.mjs` reads every quoted and backticked string in a file to
 *   find class lists. A JSDoc comment that writes `` `py-6` `` to explain the
 *   old value is indistinguishable from a template literal to that scanner,
 *   and it failed a real build over documentation.
 * - `check-nav-depth.mjs` collects every quoted string in `src/` to ask whether
 *   a label key is ever looked up. Its own header names the keys it exists to
 *   delete (`nav.more`, `nav.connections`), so a scan that read comments would
 *   find the documentation citing them and call them consumed.
 *
 * String contents are left alone, so a `//` inside a URL in an `href` is not
 * mistaken for a comment start.
 */
export function stripComments(src) {
  let out = "";
  let quote = null;
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (quote) {
      out += c;
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      quote = c;
      out += c;
      i += 1;
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") {
        out += " ";
        i += 1;
      }
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) {
        out += src[i] === "\n" ? "\n" : " ";
        i += 1;
      }
      out += "  ";
      i += 2;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}