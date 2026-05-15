"""Tool to explain the project structure and purpose."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

TOOL_ID = "project_explain"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "project"
TOOL_LABEL = "Project Explainer"
TOOL_DESCRIPTION = (
    "Analyze and explain the project structure, purpose, and key components. "
    "This tool provides a comprehensive overview of the project including: "
    "project type, main purpose, directory structure, key files, technologies used, "
    "and entry points. Use this when user asks about 'the project', 'explain this project', "
    "or wants to understand what the codebase does."
)


def execute(args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute project explanation."""
    try:
        root = Path.cwd()
        
        readme_content = ""
        if (root / "README.md").exists():
            readme_content = (root / "README.md").read_text()[:2000]
        
        todo_content = ""
        if (root / "TODO.md").exists():
            todo_content = (root / "TODO.md").read_text()[:1000]
        
        py_files = list(root.rglob("*.py"))[:20]
        py_summary = []
        for f in py_files[:10]:
            rel = f.relative_to(root)
            if "test_" not in f.name and "__pycache__" not in str(f):
                py_summary.append(str(rel))
        
        dirs = [d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        
        agent_config = ""
        if (root / "agent-config.yaml").exists():
            agent_config = (root / "agent-config.yaml").read_text()[:500]
        
        explanation = f"""Project Overview:

Directory Structure:
{', '.join(dirs[:10])}

Key Python Files:
{chr(10).join(py_summary[:5])}

{readme_content[:1000] if readme_content else '(No README found)'}

{agent_config if agent_config else ''}
"""
        
        return {"ok": True, "explanation": explanation.strip(), "files_found": len(py_files)}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}