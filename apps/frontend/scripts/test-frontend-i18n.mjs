#!/usr/bin/env node
/**
 * Full frontend i18n test suite (no extra deps):
 * 1. en ↔ de JSON key parity
 * 2. Static UI scan (hardcoded strings, t-shadowing)
 * 3. Route → page file coverage
 */
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runScanI18nUi } from "./scan-i18n-ui.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

function runNode(script) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script], {
      cwd: ROOT,
      stdio: "inherit",
    });
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${script} exited ${code}`));
    });
    child.on("error", reject);
  });
}

async function main() {
  console.log("[test] 1/2 validate-i18n.mjs (locale key parity)…");
  await runNode(join(__dirname, "validate-i18n.mjs"));

  console.log("[test] 2/2 scan-i18n-ui.mjs (routes + hardcoded UI + t-shadowing)…");
  const { ok, ui, routes } = await runScanI18nUi();
  if (!ok) {
    process.exit(1);
  }
  console.log(
    `[test] All frontend i18n checks passed (${ui.report.hardcoded.length === 0 ? "no" : "some"} hardcoded issues, routes OK).`
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
