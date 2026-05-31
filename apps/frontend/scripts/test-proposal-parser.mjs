#!/usr/bin/env node
/**
 * Unit checks for proposalParser (no extra test deps).
 */
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const TEST_TS = join(__dirname, "test-proposal-parser.ts");

function runNode(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { cwd: ROOT, stdio: "inherit" });
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`exited ${code}`));
    });
    child.on("error", reject);
  });
}

async function main() {
  await runNode(["--experimental-strip-types", TEST_TS]);
  console.log("[test] proposalParser checks passed.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
