"""Tool to explain the project structure and purpose."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

__version__ = "1.0.0"
TOOL_ID = "project_explain"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "project"
# Router phrases: co-located explain.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("project.explain",)
TOOL_LABEL = "Project Explainer"
TOOL_DESCRIPTION = (
    "Analyze and explain the project structure, purpose, and key components. "
    "This tool provides a comprehensive overview of the project including: "
    "project type, main purpose, directory structure, key files, technologies used, "
    "and entry points. Use this when user asks about 'the project', 'explain this project', "
    "or wants to understand what the codebase does."
)


def project_explain(arguments: dict[str, Any], context: dict | None = None) -> str:
    """Execute project explanation."""
    try:
        ws = workspace_binding_from_context(context)
        if ws is None:
            return json_workspace_missing_error()

        workspace_path = ws.get("path")
        
        if not workspace_path:
            return json.dumps({"ok": False, "error": "Workspace has no path configured"}, ensure_ascii=False)
        
        root = Path(workspace_path)
        
        if not root.exists():
            return json.dumps({"ok": False, "error": f"Workspace path does not exist: {root}"}, ensure_ascii=False)
        
        dirs = [d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        
        py_files = list(root.rglob("*.py"))
        py_files = [f for f in py_files if "__pycache__" not in str(f)][:20]
        
        py_summary = []
        for f in py_files[:10]:
            try:
                lines = len(f.read_text().splitlines())
                py_summary.append(f"{f.name} ({lines} lines)")
            except Exception:
                py_summary.append(f.name)
        
        readme_content = ""
        for name in ["README.md", "README.rst", "README.txt", "readme.md"]:
            readme_file = root / name
            if readme_file.exists():
                readme_content = readme_file.read_text()[:2000]
                break
        
        agent_config = ""
        if (root / "agent-config.yaml").exists():
            agent_config = (root / "agent-config.yaml").read_text()[:500]
        
        explanation = f"""Project Overview:

Directory Structure:
{', '.join(dirs[:10])}

Key Python Files:
{chr(10).join(py_summary[:5])}

{readme_content if readme_content else '(No README found)'}

{agent_config if agent_config else ''}
"""
        
        return json.dumps({"ok": True, "explanation": explanation.strip(), "files_found": len(py_files)}, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "project_explain": project_explain,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "project_explain",
            "description": "Analyze and explain the project structure, purpose, and key components.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]