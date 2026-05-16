"""Retrieval layer orchestration (fixture)."""

RETRIEVAL_LAYER_DOC = "Unified retrieve_context bundles grep and semantic search."

# bench_merge_retrieval
def merge_retrieval_results(grep_hits, semantic_hits):
    return list(grep_hits) + list(semantic_hits)
