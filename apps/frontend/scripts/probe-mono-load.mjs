#!/usr/bin/env node
/**
 * Does IBM Plex Mono actually load and paint?
 *
 * The earlier font probe read `document.fonts.check('... "IBM Plex Mono"')` once,
 * on the page right after the login redirect, and the result was recorded as
 * "unloaded on all four routes". That measurement never visited the routes for
 * mono at all — the per-route loop only read CLS. And a declared face that no
 * rendered element needed stays `unloaded` by design, so the number could not
 * distinguish "broken" from "not needed here".
 *
 * This probe answers the question directly, against the REAL built CSS and the
 * REAL served font files, with no backend required:
 *
 *   1. Is the woff2 fetchable at the URL the built CSS declares?
 *   2. Does the face reach `loaded`?
 *   3. Does text actually render in Plex Mono — proven by width against the
 *      same page with the font blocked. Same markup, same CSS, only the font
 *      withheld. If the widths are identical, the webfont is not painting and
 *      no amount of `check()` returning true would matter.
 *
 * Serves dist under the /app/ basename exactly as the app is deployed, so the
 * URL the CSS asks for is the URL being tested.
 */
import { chromium } from "playwright";
import { createServer } from "node:http";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(__dirname, "..");
const DIST = join(FRONTEND, "dist");
const PORT = 4319;

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

function findBuiltCss() {
  const dir = join(DIST, "assets");
  const files = readdirSync(dir).filter((f) => /^index.*\.css$/.test(f));
  if (!files.length) throw new Error(`kein gebautes CSS in ${dir}`);
  return files[0];
}

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".txt": "text/plain",
};

/**
 * Serves dist with the /app/ basename stripped, so a request for
 * /app/fonts/x.woff2 reads dist/fonts/x.woff2 — the same mapping the real
 * deployment has to provide.
 */
function serve(port) {
  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      const raw = decodeURIComponent((req.url || "/").split("?")[0]);
      const rel = raw.replace(/^\/app\/?/, "") || "index.html";
      const file = join(DIST, rel);
      if (!file.startsWith(DIST) || !existsSync(file)) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      res.writeHead(200, {
        "content-type": MIME[extname(file)] || "application/octet-stream",
        "cache-control": "no-store",
      });
      res.end(readFileSync(file));
    });
    server.on("error", reject);
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

const FIXTURE = (css) => `<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="/app/assets/${css}">
<style>body{margin:0;background:#0B0C0E;color:#E8EAED;padding:24px}</style>
</head>
<body>
  <span id="mono" class="font-mono text-sm">MMMMWWWWiiiii0000</span><br>
  <span id="sans" class="font-sans text-sm">MMMMWWWWiiiii0000</span>
</body>
</html>`;

async function measure({ blockMono }) {
  const server = await serve(PORT);
  const browser = await chromium.launch({
    headless: true,
    executablePath: resolveChromium(),
  });
  const requests = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 900, height: 400 } });
    const page = await ctx.newPage();
    page.on("response", (r) => {
      if (/\.woff2?($|\?)/.test(r.url())) {
        requests.push({ url: r.url().split("/").pop(), status: r.status() });
      }
    });
    if (blockMono) {
      await page.route("**/ibm-plex-mono-latin-400.woff2", (r) => r.abort());
    }
    // A real navigation to the real host, so URL resolution for the font is
    // byte-for-byte what the app gets. setContent would have run from a
    // synthetic origin and proven nothing about the /app/ mapping.
    await page.goto(`http://127.0.0.1:${PORT}/probe.html`, {
      waitUntil: "networkidle",
    });
    await page.waitForTimeout(1200);
    const out = await page.evaluate(() => {
      // A Range over the text node gives the rendered text width. getBoundingClientRect
      // on a block element would return the container and prove nothing.
      const textWidth = (id) => {
        const el = document.getElementById(id);
        const node = el && el.firstChild;
        if (!node) return null;
        const r = document.createRange();
        r.selectNodeContents(el);
        return r.getBoundingClientRect().width;
      };
      return {
        monoWidth: textWidth("mono"),
        sansWidth: textWidth("sans"),
        monoFamily: getComputedStyle(document.getElementById("mono")).fontFamily,
        checkMono: document.fonts.check('14px "IBM Plex Mono"'),
        checkSans: document.fonts.check('14px "IBM Plex Sans"'),
        faces: [...document.fonts].map((f) => `${f.family} w${f.weight}=${f.status}`),
      };
    });
    return { ...out, requests: requests.slice() };
  } finally {
    await browser.close();
    server.close();
  }
}

async function main() {
  if (!existsSync(DIST)) {
    console.error("[mono] kein dist/ — erst `npm run build`");
    process.exit(2);
  }
  const css = findBuiltCss();
  console.log(`[mono] getestet gegen gebautes CSS: ${css}`);

  // The fixture has to be served from dist so the /app/ mapping is exercised.
  const { writeFileSync } = await import("node:fs");
  writeFileSync(join(DIST, "probe.html"), FIXTURE(css));

  const withFont = await measure({ blockMono: false });
  const blocked = await measure({ blockMono: true });

  console.log("\n=== mit Font ===");
  console.log("Requests:", withFont.requests.map((r) => `${r.url}=${r.status}`).join(" ") || "keine");
  console.log("check('IBM Plex Mono'):", withFont.checkMono);
  console.log("check('IBM Plex Sans'):", withFont.checkSans);
  console.log("Faces:", withFont.faces.join(" · "));
  console.log(`mono-Breite=${withFont.monoWidth.toFixed(2)}  sans-Breite=${withFont.sansWidth.toFixed(2)}`);

  console.log("\n=== Mono blockiert (Kontrolle) ===");
  console.log("check('IBM Plex Mono'):", blocked.checkMono);
  console.log(`mono-Breite=${blocked.monoWidth.toFixed(2)}  sans-Breite=${blocked.sansWidth.toFixed(2)}`);

  const delta = Math.abs(withFont.monoWidth - blocked.monoWidth);
  const painted = delta > 0.5;
  console.log("\n=== Bewertung ===");
  console.log(`Breiten-Differenz mono (mit vs. blockiert): ${delta.toFixed(2)}px`);
  console.log(
    painted
      ? "→ Plex Mono malt tatsächlich. Die Webfont-Pipeline funktioniert."
      : "→ KEIN Unterschied: die Webfont malt nicht, es liegt am Fallback.",
  );
  const monoFetched = withFont.requests.some(
    (r) => r.url.includes("mono") && r.status === 200,
  );
  console.log(
    monoFetched
      ? "→ die woff2 wird unter der deklarierten URL ausgeliefert (200)."
      : "→ die woff2 kommt NICHT mit 200 zurück — Auslieferungsfehler.",
  );
  // The fixture lives in dist only for the duration of the run; leaving it there
  // would ship a stray page.
  const { rmSync } = await import("node:fs");
  rmSync(join(DIST, "probe.html"), { force: true });
  process.exitCode = painted && monoFetched ? 0 : 1;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
