#!/usr/bin/env node
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const TEST_TS = join(__dirname, "test-tool-step-label.ts");

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

await runNode(["--experimental-strip-types", TEST_TS]);
console.log("[test] toolStepLabel checks passed.");
