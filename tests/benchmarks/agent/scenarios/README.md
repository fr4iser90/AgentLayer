# Agent benchmark scenarios

Each scenario lives in **its own directory** — never mix scenarios in one file.

```
scenarios/
  C1_bench_marker_file/
    meta.yaml           # tier, rubric, agent_id, fixtures, …
    prompt.en.txt       # English user prompt (edit freely)
    prompt.de.txt       # German user prompt
  S2_simple_chat/
    meta.yaml
    prompt.en.txt
    prompt.de.txt
```

## Edit prompts

Open `prompt.<locale>.txt` in any scenario folder. Placeholders:

| Placeholder | Replaced at run time |
|-------------|----------------------|
| `{prefix}` | Bench run prefix, e.g. `bench-20260612T211718Z-` |
| `{friend_email}` | Friend user email (share scenarios) |
| `{hello_git_url}` | `AGENT_BENCH_GIT_URL` or default Hello-World clone URL |
| `{hello_git_branch}` | `AGENT_BENCH_GIT_BRANCH` (default `master`) |
| `{agentlayer_git_url}` | AgentLayer repo URL for security scenarios |
| `{agentlayer_git_branch}` | `AGENT_BENCH_AGENTLAYER_GIT_BRANCH` (default `main`) |

Add a new locale by creating `prompt.fr.txt` (any `prompt.<locale>.txt` is auto-discovered).

## Run locale

Set **Prompt language** in **Admin → Observability → Model benchmarks** when starting a run (stored in run config, not `.env`).

CLI:

```bash
python scripts/run_agent_benchmark.py --manifest benchmarks/manifests/coding.yaml --prompt-locale de
```

Optional env fallback for scripts only: `AGENT_BENCH_PROMPT_LOCALE=de`

## Add a scenario

1. Create `scenarios/MY_scenario_id/meta.yaml` (id must match folder name).
2. Add at least `prompt.en.txt`.
3. Register the id in `benchmarks/manifests/*.yaml`.
4. Add rubric in `tests/benchmarks/agent/rubrics.py` and catalog meta in `catalog.py`.
