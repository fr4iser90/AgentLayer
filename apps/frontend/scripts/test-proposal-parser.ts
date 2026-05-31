import assert from "node:assert/strict";
import {
  extractProposals,
  parseProposalContent,
  salvageProposalJsonText,
} from "../src/lib/proposalParser.ts";

const VALID_BLOCK = `\`\`\`json-proposal
{
  "title": "Pick one",
  "options": [
    {"id": "1", "label": "A", "description": "First"},
    {"id": "2", "label": "B", "description": "Second", "confidence": 0.8}
  ]
}
\`\`\``;

const BROKEN_LABEL_BLOCK = `\`\`\`json-proposal
{
  "title": "Wie sollen die Security Fixes durchgeführt werden?",
  "options": [
    {"id": "1", "label": "Nur HIGH Fixen", "description": "Only high"},
    {"id": "2", "label: HIGH + MEDIUM Fixen", "description": "High and medium"},
    {"id": "3", "label": "Schrittweise vorgehen", "description": "Stepwise", "confidence": 0.95}
  ]
}
\`\`\``;

assert.equal(extractProposals(VALID_BLOCK).length, 1);
assert.equal(extractProposals(VALID_BLOCK)[0]?.options.length, 2);

const salvaged = salvageProposalJsonText(`{"id": "2", "label: HIGH + MEDIUM Fixen", "description": "x"}`);
assert.ok(salvaged.includes('"label": "HIGH + MEDIUM Fixen"'));

const fixed = parseProposalContent(BROKEN_LABEL_BLOCK);
assert.equal(fixed.failedBlockCount, 0, "label typo should be salvaged");
assert.equal(fixed.proposals.length, 1);
assert.equal(fixed.proposals[0]?.options.length, 3);
assert.equal(fixed.proposals[0]?.options[1]?.label, "HIGH + MEDIUM Fixen");

const totallyBroken = parseProposalContent(
  '```json-proposal\n{ "title": "x", "options": [not json] }\n```'
);
assert.equal(totallyBroken.proposals.length, 0);
assert.equal(totallyBroken.failedBlockCount, 1);

console.log("ok");
