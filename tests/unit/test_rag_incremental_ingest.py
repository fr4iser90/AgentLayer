"""Incremental RAG markdown ingest (hash + fingerprint)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

from apps.backend.domain.rag import ingest_common as ric


def test_compute_rag_ingest_fingerprint_stable() -> None:
    rs = {
        "embedding_model": "bge-m3",
        "embedding_dim": 1024,
        "chunk_size": 1200,
        "chunk_overlap": 200,
    }
    with patch.object(ric.operator_settings, "rag_settings", return_value=rs):
        a = ric.compute_rag_ingest_fingerprint()
        b = ric.compute_rag_ingest_fingerprint()
    assert a == b
    assert len(a) == 64


def test_ingest_config_changed_when_fingerprint_differs() -> None:
    with patch.object(ric, "compute_rag_ingest_fingerprint", return_value="new"):
        assert ric.ingest_config_changed("old") is True
        assert ric.ingest_config_changed("") is True
        assert ric.ingest_config_changed("new") is False


def test_incremental_skips_unchanged_file(tmp_path: Path) -> None:
    doc = tmp_path / "a.md"
    doc.write_text("hello world\n", encoding="utf-8")
    content_hash = ric.sha256_text("hello world")
    tenant_id = 1
    user_id = uuid.uuid4()
    domain = "agentlayer_docs"
    existing = {"agentlayer-docs:a.md": {"id": 42, "content_sha256": content_hash}}

    with (
        patch("apps.backend.domain.rag.ingest_common.embed_one"),
        patch.object(ric.operator_settings, "rag_docs_ingest_fingerprint", return_value="fp"),
        patch.object(ric, "ingest_config_changed", return_value=False),
        patch(
            "apps.backend.domain.rag.ingest_common.db.rag_documents_by_tenant_domain_index",
            return_value=existing,
        ),
        patch("apps.backend.domain.rag.ingest_common.ingest_for_user") as mock_ingest,
        patch.object(ric.operator_settings, "set_rag_docs_ingest_fingerprint") as mock_set_fp,
    ):
        out = ric.ingest_markdown_paths(
            tenant_id,
            user_id,
            tmp_path,
            domain,
            [doc],
            source_uri_for_rel=lambda rel: f"agentlayer-docs:{rel}",
            title_for_rel=lambda rel: f"docs/{rel}",
            incremental=True,
        )

    mock_ingest.assert_not_called()
    mock_set_fp.assert_called_once()
    assert out["files_skipped_unchanged"] == 1
    assert out["files_ingested"] == 0


def test_incremental_reingests_when_hash_changes(tmp_path: Path) -> None:
    doc = tmp_path / "b.md"
    doc.write_text("updated\n", encoding="utf-8")
    tenant_id = 1
    user_id = uuid.uuid4()
    existing = {"agentlayer-docs:b.md": {"id": 7, "content_sha256": "stale"}}

    with (
        patch("apps.backend.domain.rag.ingest_common.embed_one"),
        patch.object(ric.operator_settings, "rag_docs_ingest_fingerprint", return_value="fp"),
        patch.object(ric, "ingest_config_changed", return_value=False),
        patch(
            "apps.backend.domain.rag.ingest_common.db.rag_documents_by_tenant_domain_index",
            return_value=existing,
        ),
        patch("apps.backend.domain.rag.ingest_common.db.rag_delete_document_by_id", return_value=True),
        patch(
            "apps.backend.domain.rag.ingest_common.ingest_for_user",
            return_value={"chunk_count": 3},
        ) as mock_ingest,
        patch.object(ric.operator_settings, "set_rag_docs_ingest_fingerprint"),
    ):
        out = ric.ingest_markdown_paths(
            tenant_id,
            user_id,
            tmp_path,
            "agentlayer_docs",
            [doc],
            source_uri_for_rel=lambda rel: f"agentlayer-docs:{rel}",
            title_for_rel=lambda rel: f"docs/{rel}",
        )

    mock_ingest.assert_called_once()
    assert out["files_ingested"] == 1
    assert out["chunk_count_total"] == 3


def test_config_change_purges_domain(tmp_path: Path) -> None:
    doc = tmp_path / "c.md"
    doc.write_text("x\n", encoding="utf-8")

    with (
        patch("apps.backend.domain.rag.ingest_common.embed_one"),
        patch.object(ric.operator_settings, "rag_docs_ingest_fingerprint", return_value="old"),
        patch.object(ric, "ingest_config_changed", return_value=True),
        patch(
            "apps.backend.domain.rag.ingest_common.db.rag_delete_documents_by_tenant_domain",
            return_value=5,
        ) as mock_purge,
        patch(
            "apps.backend.domain.rag.ingest_common.ingest_for_user",
            return_value={"chunk_count": 1},
        ),
        patch.object(ric.operator_settings, "set_rag_docs_ingest_fingerprint"),
    ):
        out = ric.ingest_markdown_paths(
            1,
            uuid.uuid4(),
            tmp_path,
            "agentlayer_docs",
            [doc],
            source_uri_for_rel=lambda rel: rel,
            title_for_rel=lambda rel: rel,
            incremental=True,
        )

    mock_purge.assert_called_once_with(1, "agentlayer_docs")
    assert out["ingest_config_changed"] is True
    assert out["purge_deleted_documents"] == 5
    assert out["incremental"] is False
