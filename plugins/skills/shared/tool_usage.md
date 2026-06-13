---
skill_id: tool_usage_discipline
exclude_agents: general
---

## Tool usage (discipline)

- The API **tools[]** list is a compact catalog; full JSON Schema for a tool is returned from **get_tool_help** when needed.
- **Do not** loop on `list_tool_categories`, `list_tools_in_category`, `list_available_tools`, or `get_tool_help`. At most one short discovery pass if you truly do not know a tool name.
- When intent is clear, **call the action tool first** (e.g. **git pull / sync repo** → `git_sync` or `bash` with `{"command":"git pull"}`; `git clone` / repo URL → `bash`; read a file → `read_file` or `read_file`).
- Use **get_tool_help at most once** per tool you are about to call with non-obvious arguments; do not repeat it every round for the same tool.
- Prefer concrete workspace tools (`git_sync`, `bash`, `read_file`, `read_file`, GitHub-related tools) over plugin meta tools (`create`, …) unless the user explicitly asks to build or install a plugin.
