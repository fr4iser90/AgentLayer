/**
 * Shared JSX opening-tag scanner.
 *
 * Both the title->Tooltip codemod and the icon-label guard need to know exactly
 * where an opening tag ends. A regex cannot answer that: `title={a > b ? x : y}`
 * contains a `>` that is not the end of the tag, and attribute values legitimately
 * contain quotes and braces. Keeping one implementation means the guard and the
 * codemod cannot drift apart — a scanner bug fixed in one but not the other is how
 * a guard starts green-lighting what it should catch.
 */

/**
 * Index just past the `>` that closes the opening tag starting at `start`
 * (which must point at the `<`). Returns -1 if the tag never closes.
 *
 * Quote state, template-literal state and brace depth are all tracked, and `>`
 * only counts as the tag end when none of them are open.
 */
export function findTagEnd(src, start) {
  let i = start + 1;
  let inSingle = false;
  let inDouble = false;
  let inTemplate = false;
  let brace = 0;
  let iter = 0;
  while (i < src.length) {
    // A tag that takes more than a few thousand steps to close is a scanner bug,
    // not real JSX. Failing loudly beats hanging on it — an earlier version spun
    // 200k times over 22 characters because two branches forgot to advance.
    if (++iter > 20000) {
      throw new Error(
        `findTagEnd: no tag end within 20000 steps from offset ${start} (brace=${brace}) — scanner bug, refusing to continue`,
      );
    }
    const c = src[i];
    // Every branch must advance i. Closing a quote without `i += 1` makes the
    // next iteration see the same quote with the state now false and re-open it,
    // oscillating forever.
    if (inSingle) {
      if (c === "\\") i += 2;
      else if (c === "'") {
        inSingle = false;
        i += 1;
      } else i += 1;
      continue;
    }
    if (inDouble) {
      if (c === "\\") i += 2;
      else if (c === '"') {
        inDouble = false;
        i += 1;
      } else i += 1;
      continue;
    }
    if (inTemplate) {
      if (c === "\\") i += 2;
      else if (c === "`") {
        inTemplate = false;
        i += 1;
      } else i += 1;
      continue;
    }
    if (c === "'") {
      inSingle = true;
      i += 1;
    } else if (c === '"') {
      inDouble = true;
      i += 1;
    } else if (c === "`") {
      inTemplate = true;
      i += 1;
    } else if (c === "{") {
      brace += 1;
      i += 1;
    } else if (c === "}") {
      brace -= 1;
      i += 1;
    } else if (c === ">" && brace === 0) return i + 1;
    else i += 1;
  }
  return -1;
}

/**
 * Find every `<name` opening tag of `name` in the source.
 * Returns { tagStart, tagEnd } pairs. Self-closing tags are reported with
 * selfClosing = true.
 */
export function findElements(src, name) {
  const open = `<${name}`;
  const found = [];
  let i = 0;
  while (i < src.length) {
    const tagStart = src.indexOf(open, i);
    if (tagStart === -1) break;
    const next = src[tagStart + open.length];
    // `<buttonbar>` is not `<button>`; only a delimiter may follow the name.
    if (next !== undefined && /[A-Za-z0-9_-]/.test(next)) {
      i = tagStart + open.length;
      continue;
    }
    const tagEnd = findTagEnd(src, tagStart);
    if (tagEnd === -1) break;
    found.push({
      tagStart,
      tagEnd,
      selfClosing: src[tagEnd - 2] === "/",
    });
    i = tagEnd;
  }
  return found;
}

/**
 * Top-level attribute names of an opening tag, in source order.
 *
 * `hasNamedAttr` answers "is there a non-empty value here", which is the wrong
 * question for a boolean prop: `<Button block>` carries `block` with no `=`, and
 * a plain substring search for `block` would equally find the word inside
 * `className="mt-4 block"` — a class is not a prop. Tokenising instead of
 * searching keeps both wrong answers out: quoted values and brace expressions
 * are skipped as units, so only names standing at the top level of the tag are
 * reported. A `{...spread}` is reported as `"..."`; whether it happens to contain
 * the attribute is not knowable here and a guard must not guess.
 */
export function attrNames(tag) {
  const names = [];
  let i = 1; // past `<`
  const skipQuoted = (quote) => {
    i += 1;
    while (i < tag.length && tag[i] !== quote) {
      if (tag[i] === "\\") i += 1;
      i += 1;
    }
    i += 1;
  };
  const skipBraces = () => {
    let depth = 0;
    while (i < tag.length) {
      const c = tag[i];
      if (c === "'" || c === '"' || c === "`") {
        skipQuoted(c);
        continue;
      }
      if (c === "{") depth += 1;
      else if (c === "}") {
        depth -= 1;
        if (depth === 0) {
          i += 1;
          return;
        }
      }
      i += 1;
    }
  };
  while (i < tag.length && /[A-Za-z0-9_.]/.test(tag[i])) i += 1; // the element name
  while (i < tag.length) {
    const c = tag[i];
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if (c === ">" || (c === "/" && tag[i + 1] === ">")) break;
    if (c === "{") {
      names.push("...");
      skipBraces();
      continue;
    }
    const start = i;
    while (i < tag.length && !/[\s=>/]/.test(tag[i])) i += 1;
    const name = tag.slice(start, i);
    if (!name) {
      i += 1;
      continue;
    }
    names.push(name);
    while (i < tag.length && /\s/.test(tag[i])) i += 1;
    if (tag[i] !== "=") continue;
    i += 1;
    const v = tag[i];
    if (v === "'" || v === '"' || v === "`") skipQuoted(v);
    else if (v === "{") skipBraces();
  }
  return names;
}

/**
 * Is `attr` present on this opening tag as a standalone attribute with a
 * non-empty value?
 *
 * The preceding-character check is what keeps `xtitle=` or `my-aria-label=` out.
 * An explicitly empty value (`aria-label=""`) hides an element from assistive
 * tech rather than naming it, so it does not count.
 */
export function hasNamedAttr(tag, attr) {
  const needle = `${attr}=`;
  let from = 0;
  while (true) {
    const at = tag.indexOf(needle, from);
    if (at === -1) return false;
    const before = at > 0 ? tag[at - 1] : "";
    if (!before || !/[A-Za-z0-9_-]/.test(before)) {
      const value = tag.slice(at + needle.length).trim();
      if (value === "") return false;
      if (
        value.startsWith('""') ||
        value.startsWith("''") ||
        value.startsWith("{}")
      ) {
        return false;
      }
      return true;
    }
    from = at + 1;
  }
}
