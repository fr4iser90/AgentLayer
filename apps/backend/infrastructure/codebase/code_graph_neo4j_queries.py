"""Query methods for the Neo4j code graph adapter."""
from __future__ import annotations

from typing import Any


class CodeGraphNeo4jQueries:
    def query_callers(self, ws: str, name: str, transitive: bool = False, max_depth: int = 5) -> list[dict[str, Any]]:
        """Who calls symbol *name*? (reverse call-graph)"""
        driver = self._get_driver()
        if driver is None:
            return []
        depth = f"*1..{max_depth}" if transitive else ""
        try:
            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH (caller:Symbol)-[:CALLS{depth}]->(target:Symbol {{name: $name, workspace_id: $ws}})
                    WHERE caller.name <> $name
                    RETURN DISTINCT caller.name AS name, caller.file_path AS file_path,
                           caller.line AS line, caller.kind AS kind
                    LIMIT 100
                    """,
                    name=name, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_callers failed: %s", exc)
            return []

    def query_callees(self, ws: str, name: str) -> list[dict[str, Any]]:
        """What does symbol *name* call? (forward call-graph)"""
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (source:Symbol {name: $name, workspace_id: $ws})-[:CALLS]->(callee:Symbol)
                    RETURN DISTINCT callee.name AS name, callee.file_path AS file_path,
                           callee.line AS line, callee.kind AS kind
                    LIMIT 100
                    """,
                    name=name, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_callees failed: %s", exc)
            return []

    def query_dependencies(self, ws: str, path: str, transitive: bool = False, max_depth: int = 5) -> list[dict[str, Any]]:
        """Which files does *path* import? (forward dependency-graph)"""
        driver = self._get_driver()
        if driver is None:
            return []
        depth = f"*1..{max_depth}" if transitive else ""
        try:
            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH (f:File {{path: $path, workspace_id: $ws}})-[:IMPORTS{depth}]->(dep:File)
                    WHERE dep.path <> $path
                    RETURN DISTINCT dep.path AS path, dep.language AS language
                    LIMIT 200
                    """,
                    path=path, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_dependencies failed: %s", exc)
            return []

    def query_dependents(self, ws: str, path: str, transitive: bool = False, max_depth: int = 5) -> list[dict[str, Any]]:
        """Which files import *path*? (reverse dependency-graph)"""
        driver = self._get_driver()
        if driver is None:
            return []
        depth = f"*1..{max_depth}" if transitive else ""
        try:
            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH (dep:File)-[:IMPORTS{depth}]->(f:File {{path: $path, workspace_id: $ws}})
                    WHERE dep.path <> $path
                    RETURN DISTINCT dep.path AS path, dep.language AS language
                    LIMIT 200
                    """,
                    path=path, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_dependents failed: %s", exc)
            return []

    def query_hierarchy(self, ws: str, name: str, direction: str = "subclasses", max_depth: int = 10) -> list[dict[str, Any]]:
        """Type hierarchy: subclasses or superclasses of *name*."""
        driver = self._get_driver()
        if driver is None:
            return []
        if direction == "superclasses":
            pattern = f"(target:Symbol {{name: $name, workspace_id: $ws}})-[:EXTENDS*1..{max_depth}]->(ancestor:Symbol)"
            ret = "ancestor"
        else:
            pattern = f"(descendant:Symbol)-[:EXTENDS*1..{max_depth}]->(target:Symbol {{name: $name, workspace_id: $ws}})"
            ret = "descendant"
        try:
            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH {pattern}
                    RETURN DISTINCT {ret}.name AS name, {ret}.file_path AS file_path,
                           {ret}.line AS line, {ret}.kind AS kind
                    LIMIT 100
                    """,
                    name=name, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_hierarchy failed: %s", exc)
            return []

    def query_impact(self, ws: str, name: str, max_depth: int = 5) -> list[dict[str, Any]]:
        """
        Impact analysis: what is transitively affected if *name* changes?

        Traverses reverse CALLS and reverse IMPORTS edges from matching symbols
        and their containing files.
        """
        driver = self._get_driver()
        if driver is None:
            return []
        try:
            with driver.session() as session:
                result = session.run(
                    f"""
                    MATCH (target:Symbol {{name: $name, workspace_id: $ws}})
                    OPTIONAL MATCH (caller:Symbol)-[:CALLS*1..{max_depth}]->(target)
                    WHERE caller.name <> $name
                    WITH collect(DISTINCT {{name: caller.name, file_path: caller.file_path,
                                            line: caller.line, kind: caller.kind, via: 'calls'}}) AS call_hits, target
                    OPTIONAL MATCH (target)-[:DEFINED_IN]->(f:File)
                    OPTIONAL MATCH (dep:File)-[:IMPORTS*1..{max_depth}]->(f)
                    WHERE dep.path <> f.path
                    WITH call_hits + collect(DISTINCT {{name: dep.path, file_path: dep.path,
                                                        line: 0, kind: 'file', via: 'imports'}}) AS all_hits
                    UNWIND all_hits AS hit
                    WITH hit WHERE hit.name IS NOT NULL
                    RETURN DISTINCT hit.name AS name, hit.file_path AS file_path,
                           hit.line AS line, hit.kind AS kind, hit.via AS via
                    LIMIT 200
                    """,
                    name=name, ws=ws,
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_impact failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # K1-lite project knowledge units
    # ------------------------------------------------------------------

    def replace_file_knowledge_units(
        self,
        workspace_id: str,
        file_path: str,
        units: list[dict[str, Any]],
    ) -> int:
        """Replace K1-lite extracted knowledge units for one file."""
        driver = self._get_driver()
        if driver is None or not self._ensure_schema():
            return 0
        fp = (file_path or "").strip().replace("\\", "/")
        if not fp:
            return 0
        rows: list[dict[str, Any]] = []
        for idx, unit in enumerate(units):
            text = str(unit.get("text") or "").strip()
            if not text:
                continue
            kind = str(unit.get("kind") or "evidence").strip().lower() or "evidence"
            line = int(unit.get("line") or 1)
            uid = f"{workspace_id}:{fp}:k1:{idx}:{line}"
            rows.append(
                {
                    "uid": uid,
                    "workspace_id": workspace_id,
                    "file_path": fp,
                    "kind": kind,
                    "label": str(unit.get("label") or text[:120]).strip()[:200],
                    "text": text[:4000],
                    "line": line,
                    "section": str(unit.get("section") or "").strip()[:240],
                    "source": str(unit.get("source") or "k1_lite").strip()[:80],
                }
            )
        try:
            with driver.session() as session:
                session.run(
                    """
                    MATCH (k:KnowledgeUnit {workspace_id: $ws, file_path: $fp})
                    DETACH DELETE k
                    """,
                    ws=workspace_id,
                    fp=fp,
                )
                if not rows:
                    return 0
                session.run(
                    """
                    MERGE (f:File {path: $fp, workspace_id: $ws})
                    WITH f
                    UNWIND $rows AS r
                    CREATE (k:KnowledgeUnit {
                        uid: r.uid,
                        workspace_id: r.workspace_id,
                        file_path: r.file_path,
                        kind: r.kind,
                        label: r.label,
                        text: r.text,
                        line: r.line,
                        section: r.section,
                        source: r.source
                    })
                    MERGE (k)-[:EVIDENCED_BY]->(f)
                    """,
                    ws=workspace_id,
                    fp=fp,
                    rows=rows,
                )
            return len(rows)
        except Exception as exc:
            logger.warning("Neo4j replace_file_knowledge_units failed for %s: %s", fp, exc)
            return 0

    def query_knowledge_units(
        self,
        workspace_id: str,
        query: str,
        *,
        kinds: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Simple lexical K1-lite evidence lookup over KnowledgeUnit nodes."""
        driver = self._get_driver()
        if driver is None or not self._ensure_schema():
            return []
        terms = [
            t.lower()
            for t in str(query or "").replace("_", " ").replace("-", " ").split()
            if len(t.strip()) >= 2
        ][:12]
        kinds_norm = [str(k).strip().lower() for k in (kinds or []) if str(k).strip()]
        try:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (k:KnowledgeUnit {workspace_id: $ws})
                    WHERE (size($kinds) = 0 OR k.kind IN $kinds)
                      AND (
                        size($terms) = 0
                        OR any(t IN $terms WHERE toLower(k.text) CONTAINS t OR toLower(k.label) CONTAINS t)
                      )
                    WITH k,
                         reduce(score = 0, t IN $terms |
                            score + CASE
                              WHEN toLower(k.label) CONTAINS t THEN 3
                              WHEN toLower(k.text) CONTAINS t THEN 1
                              ELSE 0
                            END
                         ) AS score
                    RETURN k.uid AS uid,
                           k.kind AS kind,
                           k.label AS label,
                           k.text AS text,
                           k.file_path AS file_path,
                           k.line AS line,
                           k.section AS section,
                           score AS score
                    ORDER BY score DESC, k.file_path ASC, k.line ASC
                    LIMIT $limit
                    """,
                    ws=workspace_id,
                    terms=terms,
                    kinds=kinds_norm,
                    limit=max(1, min(int(limit or 10), 50)),
                )
                return [dict(r) for r in result]
        except Exception as exc:
            logger.warning("Neo4j query_knowledge_units failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

