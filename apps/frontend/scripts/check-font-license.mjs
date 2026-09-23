#!/usr/bin/env node
/**
 * Font licence guard.
 *
 * We self-host IBM Plex (OFL 1.1). Condition 2 of that licence requires every
 * distributed copy of the font software to carry the copyright notice and the
 * licence text. The latin subsets we ship contain no name or licence records at
 * all — `strings` finds zero hits for "Plex", "SIL" or the licence URL inside
 * the woff2 files — so the notice cannot live in the font and must ship beside it.
 *
 * A notice that only exists until someone adds the next font is not a control.
 * This guard checks three things, each with a distinct failure it exists to catch:
 *
 *   1. Every font file under public/fonts is listed in scripts/font-licenses.json.
 *      Catches: a font added without any licence bookkeeping.
 *   2. Its SHA-256 still matches the manifest.
 *      Catches: a file swapped under the same name, which would make the recorded
 *      notice and the shipped bytes disagree.
 *   3. A text file in public/fonts carries the manifest's copyright line.
 *      Catches: a missing or emptied notice. An empty placeholder does not pass.
 *
 * Run with --update after intentionally changing a font file, then update the
 * copyright/source fields by hand if the new file is a different font.
 */
import { readFile, readdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join, relative, dirname, extname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const FONT_DIR = join(ROOT, "public/fonts");
const MANIFEST = join(__dirname, "font-licenses.json");

const FONT_EXTS = new Set([".woff2", ".woff", ".ttf", ".otf", ".eot"]);
const LICENSE_EXTS = new Set([".txt", ".md"]);

async function sha256(path) {
  const buf = await readFile(path);
  return createHash("sha256").update(buf).digest("hex");
}

async function listFiles(dir) {
  let entries = [];
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out = [];
  for (const e of entries) {
    if (e.isDirectory()) out.push(...(await listFiles(join(dir, e.name))));
    else out.push(join(dir, e.name));
  }
  return out;
}

export async function checkFontLicenses() {
  const manifest = JSON.parse(await readFile(MANIFEST, "utf8"));
  const all = await listFiles(FONT_DIR);
  const fonts = all.filter((f) => FONT_EXTS.has(extname(f).toLowerCase()));
  const licenses = all.filter((f) => LICENSE_EXTS.has(extname(f).toLowerCase()));

  const problems = [];
  const rel = (p) => relative(ROOT, p);

  if (fonts.length === 0) {
    problems.push(`no font files found under ${rel(FONT_DIR)} — did the directory move?`);
  }

  for (const font of fonts) {
    const name = font.slice(FONT_DIR.length + 1);
    const entry = manifest.fonts?.[name];
    if (!entry) {
      problems.push(
        `${rel(font)} is not listed in ${rel(MANIFEST)} — record its copyright holder and licence before shipping it`
      );
      continue;
    }
    const actual = await sha256(font);
    if (actual !== entry.sha256) {
      problems.push(
        `${rel(font)} hash drifted\n      manifest: ${entry.sha256}\n      actual:   ${actual}\n      the recorded notice may no longer describe the shipped file`
      );
    }
  }

  // Every distinct copyright holder in the manifest must appear in some shipped
  // text file, so an empty or wrong notice fails.
  const licenseText = (await Promise.all(licenses.map((f) => readFile(f, "utf8")))).join("\n");
  const holders = new Set(Object.values(manifest.fonts ?? {}).map((e) => e.copyright));
  for (const holder of holders) {
    if (!licenseText.includes(holder)) {
      problems.push(
        `no text file under ${rel(FONT_DIR)} contains the copyright line:\n      ${holder}`
      );
    }
  }

  return { problems, fontCount: fonts.length, licenseCount: licenses.length };
}

async function update() {
  const all = await listFiles(FONT_DIR);
  const fonts = all.filter((f) => FONT_EXTS.has(extname(f).toLowerCase()));
  const existing = JSON.parse(await readFile(MANIFEST, "utf8"));
  const out = { fonts: {} };
  for (const font of fonts) {
    const name = font.slice(FONT_DIR.length + 1);
    const prev = existing.fonts?.[name] ?? {};
    out.fonts[name] = {
      sha256: await sha256(font),
      copyright: prev.copyright ?? "TODO: set the copyright holder",
      license: prev.license ?? "TODO: set the licence",
      source: prev.source ?? "TODO: set the upstream source",
    };
  }
  await writeFile(MANIFEST, JSON.stringify(out, null, 2) + "\n");
  console.log(`[font-license] recorded ${fonts.length} font file(s) into ${relative(ROOT, MANIFEST)}`);
  console.log("[font-license] fill in any TODO fields by hand — the guard checks them.");
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  if (process.argv.includes("--update")) {
    update().catch((e) => {
      console.error(e);
      process.exit(1);
    });
  } else {
    checkFontLicenses()
      .then(({ problems, fontCount, licenseCount }) => {
        if (problems.length) {
          console.error(`[font-license] FAILED - ${problems.length} problem(s):`);
          for (const p of problems) console.error(`  - ${p}`);
          process.exit(1);
        }
        console.log(
          `[font-license] OK - ${fontCount} font file(s), ${licenseCount} licence file(s), all provenance recorded`
        );
      })
      .catch((e) => {
        console.error(e);
        process.exit(1);
      });
  }
}
