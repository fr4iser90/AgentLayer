"""Doc maintenance modes and coding_workflow validation."""

from __future__ import annotations

import pytest

from apps.backend.infrastructure.coding_workflow import normalize_coding_workflow
from apps.backend.infrastructure.doc_maintenance import (
    DOC_MAINTENANCE_MODE_BOOTSTRAP,
    DOC_MAINTENANCE_MODE_RESPECT,
    build_doc_maintenance_instructions,
    parse_doc_maintenance_mode,
)
from apps.backend.infrastructure import coding_schedule_execution as sched


def test_parse_doc_maintenance_mode_default_respect():
    assert parse_doc_maintenance_mode({}) == DOC_MAINTENANCE_MODE_RESPECT
    assert parse_doc_maintenance_mode({"doc_maintenance_mode": "bootstrap"}) == DOC_MAINTENANCE_MODE_BOOTSTRAP


def test_normalize_coding_workflow_accepts_doc_maintenance_mode():
    wf = normalize_coding_workflow(
        {
            "workspace_id": "00000000-0000-4000-8000-000000000001",
            "doc_maintenance_mode": "respect",
        },
        require_workspace=True,
    )
    assert wf["doc_maintenance_mode"] == "respect"


def test_normalize_coding_workflow_rejects_invalid_mode():
    with pytest.raises(ValueError, match="doc_maintenance_mode"):
        normalize_coding_workflow(
            {
                "workspace_id": "00000000-0000-4000-8000-000000000001",
                "doc_maintenance_mode": "unify_all",
            },
            require_workspace=True,
        )


def test_build_respect_instructions_include_profile_and_respect():
    text = build_doc_maintenance_instructions("respect")
    assert "docs/DOC_PROFILE.md" in text
    assert "Mode: respect" in text
    assert "read-only, respect project" in text


def test_build_bootstrap_instructions_allow_minimal_create():
    text = build_doc_maintenance_instructions("bootstrap")
    assert "docs/CONVENTIONS.md" in text
    assert "at most 3 new files" in text.lower()


def test_resolve_explicit_mode_uses_canonical_template():
    instr, mode = sched._resolve_doc_maintenance_instructions(
        workflow={"doc_maintenance_mode": "bootstrap"},
        title="Doc maintenance",
        stored_instructions="legacy",
    )
    assert mode == DOC_MAINTENANCE_MODE_BOOTSTRAP
    assert "legacy" not in instr
    assert "Phase 0" in instr


def test_resolve_legacy_job_prepends_preamble():
    legacy = "Scheduled documentation maintenance.\n\n## Phase 0 — Git\n1. pull"
    instr, mode = sched._resolve_doc_maintenance_instructions(
        workflow={},
        title="Doc maintenance",
        stored_instructions=legacy,
    )
    assert mode == DOC_MAINTENANCE_MODE_RESPECT
    assert legacy in instr
    assert "Mode: respect" in instr
