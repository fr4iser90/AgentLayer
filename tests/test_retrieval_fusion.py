"""RRF fusion for retrieve_context."""

from __future__ import annotations

from plugins.tools.capabilities.coding.retrieval_fusion import build_fused_ranking, reciprocal_rank_fusion


def test_rrf_promotes_dual_list_hit() -> None:
    grep = [{"path": "a.py", "line": 1, "text": "auth"}]
    sem = [{"file_path": "b.py", "line": 2, "name": "login"}]
    fused = reciprocal_rank_fusion([("code_grep", grep), ("code_semantic", sem)], limit=5)
    assert len(fused) == 2
    assert fused[0]["rank"] == 1
    assert "rrf_score" in fused[0]


def test_build_fused_ranking_dedupes_same_path() -> None:
    bundle = {
        "code_grep": {
            "ok": True,
            "matches": [{"path": "x.py", "line": 10, "text": "foo"}],
        },
        "code_semantic": {
            "ok": True,
            "results": [{"file_path": "x.py", "line": 10, "name": "foo"}],
        },
    }
    fused = build_fused_ranking(bundle, limit=10)
    assert len(fused) == 1
    assert fused[0]["path"] == "x.py"
    assert fused[0]["rrf_score"] > 0
