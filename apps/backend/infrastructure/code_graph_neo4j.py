"""Neo4j-based code graph for call-graph, dependency-graph, type hierarchy, and impact analysis."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from apps.backend.core import config

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase, Driver
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False
    Driver = None  # type: ignore[assignment,misc]


_CONSTRAINTS_CYPHER = [
    "CREATE CONSTRAINT file_path_ws IF NOT EXISTS FOR (f:File) REQUIRE (f.path, f.workspace_id) IS UNIQUE",
    "CREATE CONSTRAINT symbol_uid IF NOT EXISTS FOR (s:Symbol) REQUIRE (s.uid) IS UNIQUE",
    "CREATE INDEX symbol_name_ws IF NOT EXISTS FOR (s:Symbol) ON (s.name, s.workspace_id)",
    "CREATE INDEX file_ws IF NOT EXISTS FOR (f:File) ON (f.workspace_id)",
]


class CodeGraphNeo4j:
    """Singleton client for the code-graph Neo4j database."""

    _CONNECT_RETRY_SECONDS = 60.0

    def __init__(self) -> None:
        self._driver: Driver | None = None
        self._lock = threading.Lock()
        self._schema_ready = False
        self._connect_retry_after: float = 0.0
        self._last_connect_error: str | None = None

    def _get_driver(self) -> Driver | None:
        if not _HAS_NEO4J:
            return None
        with self._lock:
            if self._driver is not None:
                return self._driver
            if time.monotonic() < self._connect_retry_after:
                return None
            url = (config.NEO4J_URL or "").strip()
            password = (config.NEO4J_PASSWORD or "").strip()
            if not url or not password:
                return None
            try:
                self._driver = GraphDatabase.driver(
                    url,
                    auth=(config.NEO4J_USER, password),
                    max_connection_lifetime=600,
                )
                self._driver.verify_connectivity()
                self._connect_retry_after = 0.0
                self._last_connect_error = None
            except Exception as exc:
                err = str(exc)
                if err != self._last_connect_error:
                    logger.warning("Neo4j connection failed: %s", exc)
                    self._last_connect_error = err
                self._connect_retry_after = time.monotonic() + self._CONNECT_RETRY_SECONDS
                self._driver = None
                return None
            return self._driver

    def _ensure_schema(self) -> bool:
        if self._schema_ready:
            return True
        driver = self._get_driver()
        if driver is None:
            return False
        try:
            with driver.session() as session:
                for cypher in _CONSTRAINTS_CYPHER:
                    session.run(cypher)
            self._schema_ready = True
            return True
        except Exception as exc:
            logger.warning("Neo4j schema setup failed: %s", exc)
            return False

    def available(self) -> bool:
        return self._get_driver() is not None and self._ensure_schema()

    # ------------------------------------------------------------------
    # Upsert (called during coding_index)
    # ------------------------------------------------------------------

    def upsert_file_graph(
        self,
        workspace_id: str,
        file_path: str,
        language: str,
        sha256: str,
        symbols: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> int:
        """Replace all nodes/edges for *file_path* in *workspace_id* and insert fresh data."""
        driver = self._get_driver()
        if driver is None or not self._ensure_schema():
            return 0

        edges_written = 0
        try:
            with driver.session() as session:
                session.run(
                    """
                    MATCH (s:Symbol {file_path: $fp, workspace_id: $ws})
                    DETACH DELETE s
                    """,
                    fp=file_path, ws=workspace_id,
                )

                session.run(
                    """
                    MERGE (f:File {path: $fp, workspace_id: $ws})
                    SET f.language = $lang, f.sha256 = $sha
                    """,
                    fp=file_path, ws=workspace_id, lang=language, sha=sha256,
                )

                if symbols:
                    sym_rows = []
                    for s in symbols:
                        uid = f"{workspace_id}:{file_path}:{s['name']}:{s.get('line', 0)}"
                        sym_rows.append({
                            "uid": uid,
                            "name": s["name"],
                            "kind": s.get("kind", "unknown"),
                            "line": s.get("line", 0),
                            "end_line": s.get("end_line", 0),
                            "signature": s.get("signature", ""),
                            "file_path": file_path,
                            "workspace_id": workspace_id,
                        })
                    session.run(
                        """
                        UNWIND $rows AS r
                        CREATE (s:Symbol {
                            uid: r.uid,
                            name: r.name,
                            kind: r.kind,
                            line: r.line,
                            end_line: r.end_line,
                            signature: r.signature,
                            file_path: r.file_path,
                            workspace_id: r.workspace_id
                        })
                        WITH s, r
                        MATCH (f:File {path: r.file_path, workspace_id: r.workspace_id})
                        MERGE (s)-[:DEFINED_IN]->(f)
                        """,
                        rows=sym_rows,
                    )

                for rel in relationships:
                    kind = rel.get("kind", "")
                    if kind == "calls":
                        edges_written += self._upsert_call_edge(session, workspace_id, file_path, rel)
                    elif kind == "extends":
                        edges_written += self._upsert_extends_edge(session, workspace_id, file_path, rel)
                    elif kind == "implements":
                        edges_written += self._upsert_implements_edge(session, workspace_id, file_path, rel)
                    elif kind == "imports":
                        edges_written += self._upsert_import_edge(session, workspace_id, file_path, rel)

        except Exception as exc:
            logger.warning("Neo4j upsert_file_graph failed for %s: %s", file_path, exc)
            return 0
        return edges_written

    def delete_file_graph(self, workspace_id: str, file_path: str) -> bool:
        """Remove File node and all symbols/edges for one path in a workspace."""
        driver = self._get_driver()
        if driver is None or not self._ensure_schema():
            return False
        fp = (file_path or "").strip().replace("\\", "/")
        if not fp:
            return False
        try:
            with driver.session() as session:
                session.run(
                    """
                    MATCH (s:Symbol {file_path: $fp, workspace_id: $ws})
                    DETACH DELETE s
                    """,
                    fp=fp,
                    ws=workspace_id,
                )
                session.run(
                    """
                    MATCH (f:File {path: $fp, workspace_id: $ws})
                    DETACH DELETE f
                    """,
                    fp=fp,
                    ws=workspace_id,
                )
            return True
        except Exception as exc:
            logger.warning("Neo4j delete_file_graph failed for %s: %s", file_path, exc)
            return False

    def upsert_workspace_files(
        self,
        workspace_id: str,
        file_entries: list[Any],
        *,
        on_progress: Any = None,
    ) -> tuple[int, str | None]:
        """Upsert all scanned files into the graph for *workspace_id*."""
        if not self.available():
            return 0, "Neo4j unavailable"
        try:
            from plugins.tools.workspace.lib.graph_extract import resolve_import_relationships
        except ImportError:
            return 0, "coding_graph_extract not available"

        indexed_paths = {fe.path for fe in file_entries}
        total = len(file_entries)
        edges = 0
        for i, file_entry in enumerate(file_entries):
            import_rels = resolve_import_relationships(file_entry, indexed_paths)
            all_rels = [r.to_dict() for r in file_entry.relationships] + import_rels
            edges += self.upsert_file_graph(
                workspace_id=workspace_id,
                file_path=file_entry.path,
                language=file_entry.language,
                sha256=file_entry.sha256,
                symbols=[s.to_dict() for s in file_entry.symbols],
                relationships=all_rels,
            )
            if on_progress and (i % 2 == 0 or i + 1 == total):
                on_progress(i + 1, total)
        return edges, None

    @staticmethod
    def _upsert_call_edge(session: Any, ws: str, fp: str, rel: dict[str, Any]) -> int:
        result = session.run(
            """
            MATCH (caller:Symbol {name: $src, file_path: $fp, workspace_id: $ws})
            MATCH (callee:Symbol {name: $tgt, workspace_id: $ws})
            WHERE callee.kind IN ['function', 'class']
            WITH caller, callee LIMIT 1
            MERGE (caller)-[r:CALLS]->(callee)
            SET r.line = $line
            RETURN count(r) AS cnt
            """,
            src=rel["source"], tgt=rel["target"], fp=fp, ws=ws, line=rel.get("line", 0),
        )
        record = result.single()
        return int(record["cnt"]) if record else 0

    @staticmethod
    def _upsert_extends_edge(session: Any, ws: str, fp: str, rel: dict[str, Any]) -> int:
        result = session.run(
            """
            MATCH (child:Symbol {name: $src, file_path: $fp, workspace_id: $ws, kind: 'class'})
            MERGE (base:Symbol {name: $tgt, workspace_id: $ws, uid: $ws + ':?:' + $tgt + ':0'})
            ON CREATE SET base.kind = 'class', base.file_path = '?', base.line = 0,
                          base.end_line = 0, base.signature = ''
            MERGE (child)-[r:EXTENDS]->(base)
            RETURN count(r) AS cnt
            """,
            src=rel["source"], tgt=rel["target"], fp=fp, ws=ws,
        )
        record = result.single()
        return int(record["cnt"]) if record else 0

    @staticmethod
    def _upsert_implements_edge(session: Any, ws: str, fp: str, rel: dict[str, Any]) -> int:
        result = session.run(
            """
            MATCH (impl:Symbol {name: $src, file_path: $fp, workspace_id: $ws})
            MERGE (iface:Symbol {name: $tgt, workspace_id: $ws, uid: $ws + ':?:' + $tgt + ':0'})
            ON CREATE SET iface.kind = 'class', iface.file_path = '?', iface.line = 0,
                          iface.end_line = 0, iface.signature = ''
            MERGE (impl)-[r:IMPLEMENTS]->(iface)
            RETURN count(r) AS cnt
            """,
            src=rel["source"], tgt=rel["target"], fp=fp, ws=ws,
        )
        record = result.single()
        return int(record["cnt"]) if record else 0

    @staticmethod
    def _upsert_import_edge(session: Any, ws: str, fp: str, rel: dict[str, Any]) -> int:
        target_path = rel.get("target", "")
        if not target_path or target_path == fp:
            return 0
        result = session.run(
            """
            MATCH (src_f:File {path: $fp, workspace_id: $ws})
            MERGE (tgt_f:File {path: $tgt, workspace_id: $ws})
            ON CREATE SET tgt_f.language = '', tgt_f.sha256 = ''
            MERGE (src_f)-[r:IMPORTS]->(tgt_f)
            RETURN count(r) AS cnt
            """,
            fp=fp, tgt=target_path, ws=ws,
        )
        record = result.single()
        return int(record["cnt"]) if record else 0

    # ------------------------------------------------------------------
    # Query methods (called by coding_graph tool)
    # ------------------------------------------------------------------

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
    # Cleanup
    # ------------------------------------------------------------------

    def delete_workspace(self, workspace_id: str) -> bool:
        driver = self._get_driver()
        if driver is None:
            return False
        try:
            with driver.session() as session:
                session.run(
                    "MATCH (n {workspace_id: $ws}) DETACH DELETE n",
                    ws=workspace_id,
                )
            return True
        except Exception as exc:
            logger.warning("Neo4j delete_workspace failed: %s", exc)
            return False

    def close(self) -> None:
        with self._lock:
            if self._driver is not None:
                try:
                    self._driver.close()
                except Exception:
                    pass
                self._driver = None
                self._schema_ready = False


_instance: CodeGraphNeo4j | None = None
_instance_lock = threading.Lock()


def get_code_graph() -> CodeGraphNeo4j:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CodeGraphNeo4j()
        return _instance


def neo4j_status() -> dict[str, Any]:
    """Reachability probe for workspace index status UI."""
    from apps.backend.core import config

    url = (config.NEO4J_URL or "").strip()
    password = (config.NEO4J_PASSWORD or "").strip()
    if not url or not password:
        return {"configured": False, "reachable": None}
    try:
        g = get_code_graph()
        ok = g.available()
        return {"configured": True, "reachable": bool(ok)}
    except Exception as e:
        return {"configured": True, "reachable": False, "error": str(e)[:200]}
