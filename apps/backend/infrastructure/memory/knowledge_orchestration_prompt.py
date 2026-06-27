"""Prompt-only knowledge orchestration controls.

This does not enable or disable project/workspace RAG. Workspace RAG, graph,
semantic index, and docs ingestion remain project settings. The harness knob
only changes how an agent is guided to use knowledge tools when they exist.
"""

from __future__ import annotations

from apps.backend.infrastructure.agent_runtime import agent_config_effective


def build_knowledge_orchestration_snippet(*, tenant_id: int | None = None) -> str:
    if not agent_config_effective.knowledge_orchestration_enabled(tenant_id=tenant_id):
        return ""

    mode = agent_config_effective.knowledge_orchestration_mode(tenant_id=tenant_id)
    if mode == "basic_rag":
        return (
            "[Knowledge orchestration]\n"
            "Use the project's existing retrieval tools when they are available. "
            "Do not enable or disable project RAG yourself. Prefer cited files, docs, or search hits "
            "over unsupported memory. Use knowledge_query only when K1-lite has been indexed."
        )

    return (
        "[Knowledge orchestration]\n"
        "Use K1-lite knowledge orchestration over the project's existing tools. "
        "Do not enable or disable project RAG yourself; project/workspace settings remain authoritative.\n"
        "- If structured project knowledge is needed and missing, call knowledge_index once for the workspace.\n"
        "- Use knowledge_query for entities, claims, evidence, and source-backed project facts.\n"
        "- Treat retrieved knowledge as structured evidence: entities, claims, relations, methods, citations, files, and tables.\n"
        "- Prefer cross-checking claims with cited file paths, docs chunks, graph/symbol hits, or source lines before answering.\n"
        "- For unfamiliar code or docs, query existing retrieval/search tools first, then open cited paths or evidence.\n"
        "- If graph or docs retrieval is unavailable, fall back to grep/search/read_file without pretending a graph exists."
    )

