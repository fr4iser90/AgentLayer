/**
 * Safe arithmetic expressions for dashboard formula_calc blocks.
 * Supports + - * / ( ) and identifiers from an inputs map. No JS eval.
 */

export type FormulaValues = Record<string, number>;

type Tok =
  | { t: "num"; v: number }
  | { t: "id"; v: string }
  | { t: "op"; v: string }
  | { t: "lp" }
  | { t: "rp" };

function tokenize(expr: string): Tok[] {
  const s = expr.replace(/\s+/g, "");
  const out: Tok[] = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "(") {
      out.push({ t: "lp" });
      i += 1;
      continue;
    }
    if (c === ")") {
      out.push({ t: "rp" });
      i += 1;
      continue;
    }
    if ("+-*/".includes(c)) {
      out.push({ t: "op", v: c });
      i += 1;
      continue;
    }
    if (/[0-9.]/.test(c)) {
      let j = i + 1;
      while (j < s.length && /[0-9.]/.test(s[j])) j += 1;
      const n = Number(s.slice(i, j));
      if (!Number.isFinite(n)) throw new Error(`bad number near ${s.slice(i, j)}`);
      out.push({ t: "num", v: n });
      i = j;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      let j = i + 1;
      while (j < s.length && /[A-Za-z0-9_]/.test(s[j])) j += 1;
      out.push({ t: "id", v: s.slice(i, j) });
      i = j;
      continue;
    }
    throw new Error(`unexpected char ${c}`);
  }
  return out;
}

function parseEval(tokens: Tok[], values: FormulaValues): number {
  let i = 0;

  function peek(): Tok | undefined {
    return tokens[i];
  }
  function take(): Tok {
    const t = tokens[i];
    if (!t) throw new Error("unexpected end");
    i += 1;
    return t;
  }

  function parsePrimary(): number {
    const t = take();
    if (t.t === "num") return t.v;
    if (t.t === "id") {
      if (!(t.v in values) || !Number.isFinite(values[t.v])) {
        throw new Error(`missing input ${t.v}`);
      }
      return values[t.v];
    }
    if (t.t === "lp") {
      const v = parseExpr();
      const rp = take();
      if (rp.t !== "rp") throw new Error("expected )");
      return v;
    }
    if (t.t === "op" && t.v === "-") return -parsePrimary();
    throw new Error("expected value");
  }

  function parseTerm(): number {
    let v = parsePrimary();
    while (peek()?.t === "op" && (peek()!.v === "*" || peek()!.v === "/")) {
      const op = take().v;
      const r = parsePrimary();
      if (op === "*") v *= r;
      else {
        if (r === 0) throw new Error("division by zero");
        v /= r;
      }
    }
    return v;
  }

  function parseExpr(): number {
    let v = parseTerm();
    while (peek()?.t === "op" && (peek()!.v === "+" || peek()!.v === "-")) {
      const op = take().v;
      const r = parseTerm();
      v = op === "+" ? v + r : v - r;
    }
    return v;
  }

  const result = parseExpr();
  if (i !== tokens.length) throw new Error("trailing tokens");
  return result;
}

export function evaluateFormula(expr: string, values: FormulaValues): number {
  const tokens = tokenize(expr);
  return parseEval(tokens, values);
}
