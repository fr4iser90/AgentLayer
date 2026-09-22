// Renders output/mascot-lab.html and captures it for visual review.
// Run through the gate:  ./scripts/e2e-probe.sh probe-mascot.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = '/work/output/mascot-review';
const KEY_STATES = [
  'idle', 'thinking', 'working', 'focused', 'listening',
  'surprised', 'shocked', 'sleeping', 'firedUp', 'confused',
  'celebrating', 'sad', 'smug', 'overheated',
];

(async () => {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1000 },
    deviceScaleFactor: 2,
  });

  const errors = [];
  page.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') errors.push(`${m.type()}: ${m.text()}`);
  });
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));

  const url = 'file:///work/output/mascot-lab.html';
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(900);

  const state = await page.evaluate(() => ({
    buttons: document.querySelectorAll('#statebar button').length,
    stages: document.querySelectorAll('#stages .stage').length,
    cells: document.querySelectorAll('#grid .cell').length,
    readout: document.getElementById('readout').textContent,
  }));
  console.log('structure:', JSON.stringify(state));

  // 1. Live stage, one screenshot per key state.
  for (const s of KEY_STATES) {
    await page.click(`#statebar button[data-s="${s}"]`);
    await page.waitForTimeout(420);
    await page.locator('#stages').screenshot({ path: `${OUT}/stage-${s}.png` });
  }

  // 2. Small-size legibility: same SVGs forced to real avatar dimensions.
  await page.click('#statebar button[data-s="idle"]');
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.id = 'tiny';
    host.style.cssText =
      'position:fixed;left:0;top:0;z-index:9999;background:#0B0C0E;padding:14px;' +
      'display:flex;flex-direction:column;gap:12px;';
    document.body.appendChild(host);
    [48, 32, 24].forEach((px) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:10px;align-items:center;';
      const lbl = document.createElement('span');
      lbl.style.cssText =
        'color:#98A1B0;font:11px ui-monospace,monospace;width:44px;';
      lbl.textContent = px + 'px';
      row.appendChild(lbl);
      document.querySelectorAll('#stages .stage svg').forEach((svg) => {
        const c = svg.cloneNode(true);
        c.removeAttribute('style');
        c.style.width = px + 'px';
        c.style.height = px + 'px';
        c.style.background = '#1E222A';
        c.style.borderRadius = Math.max(4, px / 5) + 'px';
        row.appendChild(c);
      });
      host.appendChild(row);
    });
    // .wrap stays visible on purpose. The clones reuse the originals' gradient
    // ids; if the originals sat in a display:none subtree Chrome would treat
    // those paints as invalid and every clone would render unfilled.
  });
  await page.waitForTimeout(400);
  await page.locator('#tiny').screenshot({ path: `${OUT}/tiny-sizes.png` });

  await page.evaluate(() => {
    document.getElementById('tiny').remove();
    document.querySelector('.wrap').style.display = '';
  });

  // 3. Full 28x3 still grid.
  await page.screenshot({ path: `${OUT}/grid-full.png`, fullPage: true });

  console.log('console issues:', errors.length);
  errors.slice(0, 20).forEach((e) => console.log('  ' + e));
  console.log('wrote', OUT);
  await browser.close();
})().catch((e) => {
  console.error('PROBE FAILED:', e.message);
  process.exit(1);
});
