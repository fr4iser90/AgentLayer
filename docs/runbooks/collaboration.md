---
doc_id: runbook-collaboration
domain: agentlayer_docs
tags: [runbook, git, ci, pull-request, branch-protection]
---

## What this covers

How two (or more) people work on AgentLayer without stepping on `main`:
branching, pull requests, local precommit, and GitHub **required checks**
(gates).

## Branching (GitHub Flow)

| Branch | Role |
|--------|------|
| `main` | Always mergeable / source of truth. No direct feature work. |
| `feature/…`, `fix/…`, `docs/…` | Short-lived branches off current `main`. |

1. `git checkout main && git pull`
2. `git checkout -b feature/short-name`
3. Commit locally (precommit hook runs `precommit` profile)
4. Push and open a PR into `main`
5. Wait for CI green + one review, then merge (prefer **Squash**)
6. Delete the branch

Keep PRs small (one topic). Skip GitFlow (`develop` / `release`) unless the
team grows and needs release trains.

## Local checks (every clone)

```bash
./scripts/install-git-pre-commit-hook.sh
pip install -r requirements.txt -r requirements-dev.txt
cd apps/frontend && npm ci && cd ../..
```

Useful overrides (local only — CI still enforces):

```bash
CHECK_PROFILE=fast git commit -m "…"
SKIP_CHECKS=node_cve_full,python_cve git commit -m "…"
SKIP_PRE_COMMIT=1 git commit -m "…"   # last resort
```

Profiles live in `scripts/checks/config.json`. Same runner as CI:

```bash
python3 scripts/checks/run.py --profile precommit
python3 scripts/checks/run.py --profile ci
```

## CI gate

Workflow: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)

- Triggers on every PR and on pushes to `main`
- Runs `python scripts/checks/run.py --profile ci` with `CHECK_STRICT_TOOLS=1`
- Job / status check name: **`CI / checks`**

Precommit can be skipped on a laptop; this job cannot once it is required on
`main`.

## Branch protection checklist (GitHub)

Repo → **Settings** → **Rules** → **Rulesets** (or classic **Branches** →
Branch protection rule) for `main`:

- [ ] Restrict updates to matching branches / apply to `main`
- [ ] Require a pull request before merging
- [ ] Require approvals: **1** (optional while solo; recommended with a
      collaborator)
- [ ] Require status checks to pass: add **`CI / checks`**
  - First open a PR (or push to `main`) so the check appears in the picker
- [ ] Do **not** allow administrators to bypass (or you will skip the gate)
- [ ] Optional: require linear history + allow **Squash** merge only
- [ ] Optional: delete branch on merge

After the first green CI run, confirm the required check name matches exactly
(`CI / checks`).

## Review habits

- Author: short PR body — what / why / how to test
- Reviewer: skim diff + trust green `CI / checks`; dig into domain/API/auth
  changes
- Prefer squash merge so `main` stays a readable timeline
