import assert from "node:assert/strict";
import { formatToolStepLabel } from "../src/features/chat/toolStepLabel.ts";

assert.equal(
  formatToolStepLabel(
    "coding_bash",
    "command=git diff foo.py",
    "Coding: Bash",
    "Coding: Bash git diff foo.py",
  ),
  "Coding: Bash git diff foo.py",
);

assert.equal(
  formatToolStepLabel("coding_bash", "command=x", "Coding: Bash", undefined),
  "Coding: Bash",
);

assert.equal(formatToolStepLabel(undefined, undefined, undefined, "SimpleSecCheck: findings limit=200"), "SimpleSecCheck: findings limit=200");

console.log("ok");
