"""Materialize an approved agent submission into the ``plugins/agents`` store (P7a).

Writes ``<plugins_dir>/<id>/agent.yaml`` from the persisted JSONB definition plus
``system_prompt.md`` when provided, then optionally reloads the agent registry so
the promoted agent is live without a restart. Filesystem writes are best-effort:
an ``OSError`` is captured in the returned ``error`` (and recorded on the
submission) rather than aborting an already-approved review.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

logger = logging.getLogger(__name__)


def _plugins_dir(base: Optional[Path]) -> Path:
    if base is not None:
        return Path(base)
    try:
        from apps.backend.domain.agent_runtime.registry import agent_plugin_dirs

        dirs = agent_plugin_dirs()
        if dirs:
            return Path(dirs[0])
    except Exception:  # noqa: BLE001 - fall back to the conventional path
        pass
    return Path("plugins/agents")


def materialize_submission(
    *,
    submission: dict[str, Any],
    plugins_dir: Optional[Path] = None,
    reload_agent_registry: Optional[Callable[[], None]] = None,
) -> dict[str, Any]:
    slug = str(submission.get("agent_id") or "").strip()
    if not slug:
        return {"ok": False, "error": "submission has no agent_id", "written": []}
    payload = submission.get("agent_yaml")
    if not isinstance(payload, dict) or not payload:
        return {"ok": False, "error": "submission has no agent_yaml definition", "written": []}
    prompt = submission.get("system_prompt")

    dest_dir = _plugins_dir(plugins_dir) / slug
    written: list[str] = []
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = dest_dir / "agent.yaml"
        definition = dict(payload)
        definition.setdefault("system_prompt_file", "system_prompt.md")
        yaml_path.write_text(
            yaml.safe_dump(definition, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        written.append(str(yaml_path))
        if prompt:
            prompt_path = dest_dir / "system_prompt.md"
            prompt_path.write_text(prompt, encoding="utf-8")
            written.append(str(prompt_path))
    except OSError as exc:
        logger.warning("failed to materialize agent %s: %s", slug, exc)
        return {"ok": False, "error": f"filesystem write failed: {exc}", "written": written}

    if reload_agent_registry is not None:
        try:
            reload_agent_registry()
        except Exception as exc:  # noqa: BLE001 - reload must never fail a review
            logger.warning("agent registry reload failed after materializing %s: %s", slug, exc)

    logger.info("materialized agent %s -> %s", slug, dest_dir)
    return {"ok": True, "written": written, "agent_id": slug}
