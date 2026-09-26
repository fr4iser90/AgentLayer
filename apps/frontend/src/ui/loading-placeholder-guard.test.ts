import { describe, expect, it } from "vitest";
import {
  diffBaseline,
  scanLoadingPlaceholders,
} from "../../scripts/check-loading-placeholder.mjs";
import { stripComments } from "../../scripts/strip-comments.mjs";

/**
 * One rule: a loading branch that is replaced by a repeated structure has to
 * reserve the height of that structure.
 *
 * The rule lives or dies on where it stops. Every test below plants the source
 * that would break it in one specific direction — flagging a `status` decision
 * that is not a loading state, missing a violation because a class list holds
 * `min(60vh,420px)`, treating `loading ?? <List />` as a ternary, or calling a
 * renderer helper a violation — because a guard that fires on the wrong thing
 * gets silenced, and a guard that misses the right thing keeps the shift.
 */

const hits = (src: string) => scanLoadingPlaceholders("src/pages/Planted.tsx", stripComments(src));

describe("scanLoadingPlaceholders", () => {
  it("flags a text line that is replaced by a mapped list", () => {
    const found = hits(`
      function P() {
        return loading ? <p className="text-sm">{t("a:loading")}</p> : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
      }
    `);
    expect(found).toHaveLength(1);
    expect(found[0].flag).toBe("loading");
  });

  it("accepts a branch that already reserves height", () => {
    expect(
      hits(`
        function P() {
          return loading ? <SkeletonRows rows={3} rowHeight={98} /> : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
        }
      `)
    ).toEqual([]);
    expect(
      hits(`
        function P() {
          return detailLoading ? <div className="animate-pulse h-9 rounded-tile" /> : <table><tbody>{rows.map((r) => <tr key={r.id} />)}</tbody></table>;
        }
      `)
    ).toEqual([]);
  });

  it("counts a list that reaches the screen through the Table primitive", () => {
    // Moving a hand-rolled table onto `ui/Table` deletes the word `table` from
    // the loaded arm and leaves the rows that arrive exactly as tall. If only
    // the tag counted, every adoption would clear a violation it never fixed.
    expect(
      hits(`
        function P() {
          return loading ? <p className="text-xs">{t("a:loading")}</p> : <Table columns={cols} rows={rows} rowKey={(r) => r.id} />;
        }
      `)
    ).toHaveLength(1);
    // A component that renders no list stays out of reach: its height lives
    // inside it and the guard does not guess.
    expect(
      hits(`
        function P() {
          return loading ? <p className="text-xs">{t("a:loading")}</p> : <EmptyState hint={t("a:none")} />;
        }
      `)
    ).toEqual([]);
  });

  it("leaves a decision that is not a loading state alone", () => {
    expect(
      hits(`
        function P() {
          return status === "ready" ? <Badge>ok</Badge> : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
        }
      `)
    ).toEqual([]);
  });

  it("leaves a branch whose flag is negated — that arm is the empty state", () => {
    // `!loading` puts the absence of loading in the condition, so the text arm
    // means "there is nothing", not "wait". Reserving there would hold space for
    // records that never come, and the guard would be asking for a placeholder
    // over an honest empty message.
    expect(
      hits(`
        function P() {
          return visible.length === 0 && !loading ? <li className="py-base text-xs">{t("a:none")}</li> : visible.map((e) => <li key={e.id} />);
        }
      `)
    ).toEqual([]);
    expect(
      hits(`
        function P() {
          return !runsLoading ? <ul>{runs.map((r) => <li key={r.id} />)}</ul> : <p>{t("a:loading")}</p>;
        }
      `)
    ).toEqual([]);
  });

  it("leaves a branch that gains a single block, not a list", () => {
    expect(
      hits(`
        function P() {
          return loading ? <p className="text-sm">{t("a:loading")}</p> : <section className="rounded-sheet"><h2>{title}</h2></section>;
        }
      `)
    ).toEqual([]);
  });

  it("splits the arms across a parens-in-class list and a nested ternary", () => {
    // `max-h-[min(60vh,420px)]` puts non-call parens inside the first arm, and
    // the loaded arm chains another ternary: either one read wrong hides every
    // dropdown list in the app.
    const found = hits(`
      function P() {
        return (
          <div className="max-h-[min(60vh,420px)] overflow-y-auto">
            {loading ? (
              <p className="text-sm">{t("a:loading")}</p>
            ) : failed ? (
              <p className="text-sm">{t("a:failed")}</p>
            ) : (
              <ul>{items.map((i) => <li key={i.id} />)}</ul>
            )}
          </div>
        );
      }
    `);
    expect(found).toHaveLength(1);
  });

  it("does not read a comparison operator as a tag", () => {
    const found = hits(`
      function P() {
        return loading ? <p>{t("a:loading")}</p> : count < 2 ? <p>{t("a:few")}</p> : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
      }
    `);
    expect(found).toHaveLength(1);
  });

  it("does not read a coalescing operator as a ternary", () => {
    expect(
      hits(`
        function P() {
          return loading ?? <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
        }
      `)
    ).toEqual([]);
  });

  it("does not guess the height behind a renderer helper, but does guess a translation", () => {
    expect(
      hits(`
        function P() {
          return listLoading ? loadingRows(6, t("a:loading")) : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
        }
      `)
    ).toEqual([]);
    expect(
      hits(`
        function P() {
          return listLoading ? t("a:loading") : <ul>{rows.map((r) => <li key={r.id} />)}</ul>;
        }
      `)
    ).toHaveLength(1);
  });

  it("ignores a JSX example written in a comment", () => {
    expect(
      scanLoadingPlaceholders(
        "src/pages/Planted.tsx",
        stripComments(`
          /**
           * Do not write: loading ? <p>{t("a:loading")}</p> : <ul>{rows.map((r) => <li />)}</ul>
           */
          function P() {
            return null;
          }
        `)
      )
    ).toEqual([]);
  });
});

describe("diffBaseline", () => {
  it("fails a file that grew past its recorded count", () => {
    const { grew } = diffBaseline({ "src/a.tsx": 1 }, new Map([["src/a.tsx", 2]]));
    expect(grew).toEqual([{ rel: "src/a.tsx", n: 2, allowed: 1 }]);
  });

  it("counts a new unrecorded file against zero", () => {
    const { grew } = diffBaseline({}, new Map([["src/new.tsx", 1]]));
    expect(grew).toHaveLength(1);
  });

  it("only reports a file that went down as stale", () => {
    const { grew, stale } = diffBaseline({ "src/a.tsx": 3 }, new Map([["src/a.tsx", 1]]));
    expect(grew).toEqual([]);
    expect(stale).toEqual([{ rel: "src/a.tsx", was: 3, now: 1 }]);
  });
});