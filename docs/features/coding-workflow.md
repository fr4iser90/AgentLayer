# Coding Workflow

This document describes the isolated coding workflow for the AgentLayer coding agent.

## Overview

The coding agent works in an **isolated workspace** to prevent accidental modifications to the host codebase.

```
Host Machine          Docker Container
         ┌───────────────────────┐
         │                       │
  /workspace/AgentLayer  ┌─ Container ──┐
  (YOUR CODE)           │             │
                      │   /code    │ ← Agent workspace (read-only from host)
                      │  (volume) │
                      │             │
                      └───────────┘
```

## Architecture

### Root Isolation

| Path | Access | Purpose |
|------|--------|---------|
| `/workspace/AgentLayer` (host) | Read-only | Source of Truth |
| `/code` (container) | Read-write | Agent workspace |

The container mounts the host code as **read-only**:

```yaml
# compose.yaml
volumes:
  - .:/code:ro    # colon + ro = read-only
```

### Why This Matters

- Agent **cannot** modify host-code directly
- Changes stay in `/code` (Docker volume)
- You review changes before merging
- Fork bombs and `rm -rf /` are blocked

## Workflow

### 1. Start Session

```
User: "Refactor the logging system"
         │
         ▼
┌─────────────────────────────┐
│ Agent receives task         │
│ Runs coding_index to       │
│ understand codebase      │
└─────────────────────────────┘
```

### 2. Plan

Agent presents options as JSON:

```json
{
  "title": "How should I approach this?",
  "options": [
    {"id": "1", "label": "Quick fix", "description": "...", "confidence": 0.9},
    {"id": "2", "label": "Full refactor", "description": "...", "confidence": 0.7}
  ]
}
```

### 3. User Selects Option

```
User clicks option → Agent proceeds
```

### 4. Validate (Required!)

Before reporting success, agent MUST validate:

```bash
# Python files
ruff check .

# Or compile check
python -m py_compile 

# JavaScript/TypeScript
npm run lint
npm run typecheck
```

**Rule**: If validation fails → fix issues, don't ignore them.

### 5. Review

Changes stay in `/code`. You review via:

```bash
# Show changes
git diff

# Or compare to main
git diff main...agent/session-xyz
```

### 6. Merge (Manual)

Only you merge changes to your host codebase.

## Available Tools

| Tool | Purpose |
|------|---------|
| `coding_read` | Read file contents |
| `coding_write` | Create new file |
| `edit` | Edit a file |
| `replace` | Replace a pattern |
| `glob` | Find files by pattern |
| `search` | Search in files |
| `retrieve_context` | Grep + semantic (Qdrant) + RAG docs (+ optional memory) in one call |
| `index` | Build symbol index |
| `bash` | Run shell commands |
| `symbols` | List symbols in file |

### Tool Guidelines

#### coding_glob

```
REQUIRED: pattern (glob like **/*.py, src/**/*.ts)
OPTIONAL: path (base directory)
```

**Common patterns**:
- `*.py` - all Python files
- `**/*.py` - recursive
- `src/**/*.ts` - TypeScript in src/

#### coding_bash

Blocked commands:
- `rm -rf /`
- `mkfs`, `fdisk`
- `iptables`, `ufw`

Allowed validation:
- `ruff check .`
- `python -m py_compile`
- `npm test`, `npm run lint`

## System Prompt

The agent receives this guidance:

```
You work in an ISOLATED workspace at /code.

RULES:
1. NEVER edit files outside /code
2. ALWAYS validate after changes
3. If validation fails: fix, don't ignore
4. Use 'index' tool first
5. No dangerous commands
```

## Troubleshooting

### "pattern is required"

Use `pattern` parameter, not `path`:

```json
// ✅ Correct
{"pattern": "**/*.py"}

// ❌ Wrong
{"path": "**/*.py"}
```

### "coding root not found"

Check Docker volume mount:

```bash
docker compose exec agent-layer ls /code
```

### Agent ignores validation

System prompt rules say:

> If validation fails: fix the issues, do NOT ignore them

If agent reports success without validation, ask:

> "Please validate with ruff check first"

### Git Workflow (Optional)

For full isolation, use branches:

```bash
# On host
git checkout -b agent/session-123

# After review
git diff main
git merge agent/session-123
```

## Best Practices

1. **Always use coding_index first** - Agent understands the codebase
2. **Review before merge** - Don't trust blindly
3. **Specify validation** - "Run ruff check after changes"
4. **Use proposals** - Agent shows options, you choose
5. **Ask for clarification** - If unsure, agent should ask

## Future Enhancements

- [ ] Automatic git branch per session
- [ ] Workspace snapshots for rollback
- [ ] CI/CD validation in container
- [ ] Pull request automation