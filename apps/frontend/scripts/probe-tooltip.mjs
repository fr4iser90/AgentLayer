#!/usr/bin/env node
/**
 * Tooltip browser probe.
 *
 * The unit tests cover the placement arithmetic and the state machine. They
 * cannot cover the three things that actually decide whether this component works
 * in the app, because jsdom performs no layout and has no PointerEvent:
 *
 *   1. Does the portalled bubble escape an `overflow:hidden` / `overflow-x:auto`
 *      ancestor? Verified with document.elementFromPoint at the bubble's own
 *      centre: if an ancestor clipped it, that point would resolve to something
 *      else.
 *   2. Does it really flip against the viewport edge?
 *   3. Does a real touch pointer stay out of the way?
 *
 * Builds the fixture in scripts/tooltip-probe to a throwaway directory, serves
 * it, drives Chromium, and cleans up. Nothing here touches the app build.
 */
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const PROBE = join(FRONTEND, "scripts/tooltip-probe");
const DIST = join(PROBE, ".probe-dist");

const HOVER_DELAY = 500;
const SETTLE = 120;

function resolveChromium() {
  if (process.env.CHROMIUM_PATH && existsSync(process.env.CHROMIUM_PATH)) {
    return process.env.CHROMIUM_PATH;
  }
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    join(process.env.HOME || "", ".cache/ms-playwright"),
  ].filter(Boolean);
  for (const root of roots) {
    if (!existsSync(root)) continue;
    const builds = readdirSync(root)
      .filter((d) => /^chromium-\d+$/.test(d))
      .sort((a, b) => parseInt(b.split("-")[1], 10) - parseInt(a.split("-")[1], 10));
    for (const build of builds) {
      for (const dir of ["chrome-linux64", "chrome-linux"]) {
        const p = join(root, build, dir, "chrome");
        if (existsSync(p)) return p;
      }
    }
  }
  return undefined;
}

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".map": "application/json",
  ".woff2": "font/woff2",
};

function serve(dir, port) {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const rel = decodeURIComponent((req.url || "/").split("?")[0]);
      const file = join(dir, rel === "/" ? "index.html" : rel.replace(/^\//, ""));
      if (!existsSync(file) || !file.startsWith(dir)) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      res.writeHead(200, { "content-type": MIME[extname(file)] || "application/octet-stream" });
      res.end(readFileSync(file));
    });
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

const results = [];
function check(name, pass, detail = "") {
  results.push({ name, pass, detail });
  console.log(`${pass ? "  OK  " : " FEHLT"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
  console.log("[probe] baue Fixture…");
  const build = spawnSync(
    "npx",
    ["vite", "build", "--config", join(PROBE, "vite.probe.config.mjs")],
    { cwd: FRONTEND, stdio: "inherit" },
  );
  if (build.status !== 0) throw new Error("fixture build failed");

  const port = 4317;
  const server = await serve(DIST, port);
  const base = `http://127.0.0.1:${port}`;
  const exe = resolveChromium();
  const browser = await chromium.launch({
    executablePath: exe,
    args: exe ? [] : undefined,
  });

  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(base, { waitUntil: "networkidle" });

    const tip = () => page.locator('[role="tooltip"]');
    const hover = async (sel) => {
      await page.hover(sel);
      await page.waitForTimeout(HOVER_DELAY + SETTLE);
    };

    // --- 1. portal structure -------------------------------------------------
    await hover("#t-clip");
    const struct = await page.evaluate(() => {
      const t = document.querySelector('[role="tooltip"]');
      if (!t) return null;
      const cs = getComputedStyle(t);
      return {
        parentIsBody: t.parentElement === document.body,
        position: cs.position,
        text: t.textContent,
      };
    });
    check(
      "Bubble ist ein Kind von document.body (Portal, position fixed)",
      !!struct && struct.parentIsBody && struct.position === "fixed",
      struct ? `parent=${struct.parentIsBody ? "body" : "?"} position=${struct.position}` : "keine Bubble",
    );

    // --- 2. not clipped by overflow:hidden -----------------------------------
    // The clipping condition that matters is "any part of the bubble lies above
    // the container's top edge". An absolutely positioned child there would be
    // cut off; elementFromPoint at that part still resolving to the bubble is
    // the proof it is painted. Requiring the bubble to clear the edge entirely
    // would be a stricter bar than the bug.
    const clip = await page.evaluate(() => {
      const t = document.querySelector('[role="tooltip"]');
      const box = document.getElementById("clipbox");
      if (!t || !box) return null;
      const r = t.getBoundingClientRect();
      const br = box.getBoundingClientRect();
      const cx = r.x + r.width / 2;
      // Midpoint of the overhang region: inside the bubble and above the
      // container's top edge, which is exactly where a clipped child would be
      // missing.
      const cy = (r.top + br.top) / 2;
      const hit = document.elementFromPoint(cx, cy);
      return {
        pokesAboveBox: r.top < br.top,
        overhangPx: Math.round(br.top - r.top),
        paintedAboveEdge: hit === t || (hit && t.contains(hit)),
        hitTag: hit ? hit.tagName : "null",
        tipTop: Math.round(r.top),
        boxTop: Math.round(br.top),
      };
    });
    check(
      "Bubble ragt ueber die overflow:hidden-Box hinaus und wird dort gemalt",
      !!clip && clip.pokesAboveBox && clip.paintedAboveEdge,
      clip
        ? `ueberstand=${clip.overhangPx}px (tip.top=${clip.tipTop} box.top=${clip.boxTop}) elementFromPoint=${clip.hitTag}`
        : "nichts",
    );

    // --- 2b. control: prove this test can detect clipping at all -------------
    // Without this the passing check above is unfalsifiable. An absolutely
    // positioned sibling in the same geometry must NOT be hit-testable above
    // the container's edge; if it were, elementFromPoint would not be telling
    // us anything about the portal.
    const control = await page.evaluate(() => {
      const box = document.getElementById("clipbox");
      const probe = document.createElement("div");
      probe.id = "abs-control";
      probe.style.cssText =
        "position:absolute;left:8px;top:-30px;width:120px;height:24px;background:#F85149;z-index:9999";
      box.style.position = "relative";
      box.appendChild(probe);
      const r = probe.getBoundingClientRect();
      const br = box.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + 10, (r.top + br.top) / 2);
      const visible = probe.checkVisibility
        ? probe.checkVisibility({ visibilityProperty: true, opacityProperty: true })
        : null;
      const hitIsProbe = hit === probe;
      probe.remove();
      return { clipped: !hitIsProbe, hitTag: hit ? hit.tagName : "null", visible };
    });
    check(
      "Kontrolle: ein absolut positioniertes Kind WIRD von overflow:hidden abgeschnitten",
      control.clipped,
      `elementFromPoint=${control.hitTag} (rot, das abs-Kind trifft die Maus dort nicht)`,
    );

    // --- 3. not clipped by overflow-x:auto -----------------------------------
    await page.mouse.move(5, 5);
    await page.waitForTimeout(250);
    await hover("#t-scroll");
    const scroll = await page.evaluate(() => {
      const t = document.querySelector('[role="tooltip"]');
      const box = document.getElementById("scrollbox");
      if (!t || !box) return null;
      const r = t.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return { painted: hit === t || (hit && t.contains(hit)), hitTag: hit ? hit.tagName : "null" };
    });
    check(
      "Bubble entkommt overflow-x:auto",
      !!scroll && scroll.painted,
      scroll ? `elementFromPoint=${scroll.hitTag}` : "nichts",
    );

    // --- 4. flips at the viewport top edge -----------------------------------
    await page.mouse.move(5, 5);
    await page.waitForTimeout(250);
    await hover("#t-top");
    const flip = await page.evaluate(() => {
      const t = document.querySelector('[role="tooltip"]');
      const b = document.getElementById("t-top");
      if (!t || !b) return null;
      const tr = t.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return { below: tr.top >= br.bottom, inViewport: tr.top >= 0 && tr.bottom <= innerHeight };
    });
    check(
      "klappt an der oberen Viewport-Kante nach unten",
      !!flip && flip.below && flip.inViewport,
      flip ? `unterhalb=${flip.below} im Viewport=${flip.inViewport}` : "nichts",
    );

    // --- 5. long label respects max width ------------------------------------
    await page.mouse.move(5, 5);
    await page.waitForTimeout(250);
    await hover("#t-long");
    const wide = await page.evaluate(() => {
      const t = document.querySelector('[role="tooltip"]');
      if (!t) return null;
      const r = t.getBoundingClientRect();
      return { width: Math.round(r.width), inViewport: r.left >= 0 && r.right <= innerWidth };
    });
    check(
      "langer Tooltip bleibt unter der Maximalbreite und im Viewport",
      !!wide && wide.width <= 260 && wide.inViewport,
      wide ? `breite=${wide.width}px` : "nichts",
    );

    // --- 6. hoverable: pointer can reach a link inside the bubble ------------
    await page.mouse.move(5, 5);
    await page.waitForTimeout(250);
    await hover("#t-link");
    const linkReachable = await page.evaluate(() => {
      const a = document.getElementById("tip-link");
      if (!a) return false;
      const r = a.getBoundingClientRect();
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return hit === a;
    });
    check("Link im Tooltip ist mit der Maus erreichbar", linkReachable);
    // Crossing onto the bubble must not close it.
    await page.hover("#tip-link");
    await page.waitForTimeout(400);
    check(
      "Bubble bleibt offen, wenn die Maus auf ihr steht",
      (await tip().count()) === 1,
    );

    // --- 7. keyboard: real Tab, not page.focus() -----------------------------
    // Chrome only sets :focus-visible for keyboard-initiated focus. A
    // programmatic element.focus() reports false, so driving this with
    // page.focus() would measure the wrong thing and look like a component bug.
    await page.mouse.move(5, 5);
    await page.waitForTimeout(300);
    await page.evaluate(() => document.body.focus());
    const focusProbe = await page.evaluate(() => {
      const b = document.getElementById("t-clip");
      b.focus();
      const programmatisch = b.matches(":focus-visible");
      return { programmatisch };
    });
    await page.evaluate(() => document.activeElement?.blur());
    await page.waitForTimeout(150);

    // Tab from the top of the document until the clip trigger is reached.
    let reached = false;
    for (let i = 0; i < 12 && !reached; i += 1) {
      await page.keyboard.press("Tab");
      const id = await page.evaluate(() => document.activeElement?.id);
      if (id === "t-clip") reached = true;
    }
    await page.waitForTimeout(SETTLE);
    const openedByTab = (await tip().count()) === 1;
    check(
      "Tab-Fokus oeffnet den Tooltip",
      reached && openedByTab,
      `erreicht=${reached} bubble=${openedByTab} (programmatischer Fokus: focus-visible=${focusProbe.programmatisch}, oeffnet also bewusst nicht)`,
    );
    await page.keyboard.press("Escape");
    await page.waitForTimeout(SETTLE);
    const focusBack = await page.evaluate(() => document.activeElement?.id);
    check(
      "Escape schliesst und gibt den Fokus zurueck",
      (await tip().count()) === 0 && focusBack === "t-clip",
      `activeElement=${focusBack}`,
    );

    // --- 8. real touch does not open a hover bubble --------------------------
    const tctx = await browser.newContext({ viewport: { width: 480, height: 800 }, hasTouch: true });
    const tpage = await tctx.newPage();
    await tpage.goto(base, { waitUntil: "networkidle" });
    await tpage.locator("#t-clip").tap();
    await tpage.waitForTimeout(HOVER_DELAY + 400);
    const touchBubbles = await tpage.locator('[role="tooltip"]').count();
    check("Touch oeffnet keinen Hover-Tooltip", touchBubbles === 0, `anzahl=${touchBubbles}`);
    const touchType = await tpage.evaluate(() => {
      return new Promise((resolve) => {
        const b = document.getElementById("t-scroll");
        b.addEventListener("pointerdown", (e) => resolve(e.pointerType), { once: true });
        b.dispatchEvent(new PointerEvent("pointerdown", { pointerType: "touch", bubbles: true }));
      });
    });
    check("echter Browser liefert pointerType='touch'", touchType === "touch", `wert=${touchType}`);

    const failed = results.filter((r) => !r.pass);
    console.log(
      `\n[probe] ${results.length - failed.length}/${results.length} Pruefungen bestanden`,
    );
    if (failed.length) {
      console.error("[probe] FEHLGESCHLAGEN:");
      for (const f of failed) console.error(`  - ${f.name} ${f.detail}`);
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => {
  console.error("[probe] Fehler:", e);
  process.exit(1);
});
