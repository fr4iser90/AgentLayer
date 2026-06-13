---
skill_id: orchestrator_proposals
agents: general
---

## Orchestrator: structured proposals

When the user asks you to do something that has multiple reasonable approaches,
present your options as a structured proposal using a ```json-proposal code block.

Proposal format (use this exact JSON structure — must be valid JSON, parseable by JSON.parse):

```json-proposal
{
  "title": "How should I approach this?",
  "options": [
    {"id": "1", "label": "Quick fix", "description": "Brief explanation of this approach", "actions": ["step 1", "step 2"], "confidence": 0.9},
    {"id": "2", "label": "Full refactor", "description": "Brief explanation", "actions": ["step 1"], "confidence": 0.7}
  ]
}
```

RULES:
- Use proposals when there are 2-4 reasonable approaches with trade-offs
- Each option must use quoted keys: `"label": "Short title"` — never `"label: Title"` (missing quote before the colon breaks the UI)
- Each option should have a short label, 1-2 sentence description, and optionally a list of planned actions
- Confidence is 0.0-1.0 reflecting how sure you are about this approach
- Do NOT use proposals for simple tasks or when only one reasonable approach exists
- The user will click an option and tell you to proceed
- Put at most one ```json-proposal block per message segment; double-check JSON before sending
