"""Discover dashboard domains under ``plugins/dashboards/*/`` via ``dashboard.kind.json``."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_KIND_MARKERS = ("dashboard.kind.json", "template.manifest.json")


def dashboard_tree_root() -> Path:
    """Plug-and-play dashboard bundles: ``PLUGINS_DIR/dashboards/<domain>/``."""
    from apps.backend.core.config import PLUGINS_DIR
    return PLUGINS_DIR / "dashboards"


def _safe_relative_file(bundle_dir: Path, rel: str, label: str) -> Path:
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise ValueError(f"{label}: invalid path {rel!r}")
    parts = Path(raw).parts
    if ".." in parts:
        raise ValueError(f"{label}: path must not contain '..' ({rel!r})")
    out = (bundle_dir / raw).resolve()
    root = bundle_dir.resolve()
    try:
        out.relative_to(root)
    except ValueError as e:
        raise ValueError(f"{label}: path escapes bundle directory ({rel!r})") from e
    return out


@dataclass(frozen=True)
class KindBundle:
    """One gallery bundle (``dashboard.kind.json`` or ``template.manifest.json``)."""

    bundle_dir: Path
    template_id: str
    kind: str
    label: str | None
    description: str | None
    template: Path | None
    schema_sql: Path | None
    setup: Path | None


def _parse_bundle(marker: Path) -> KindBundle | None:
    bundle_dir = marker.parent
    try:
        raw = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("skip invalid dashboard.kind.json %s: %s", marker, e)
        return None
    if not isinstance(raw, dict):
        logger.warning("skip dashboard.kind.json (not object): %s", marker)
        return None
    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        logger.warning("skip dashboard.kind.json (missing kind): %s", marker)
        return None
    kind_n = kind.strip().lower()

    template_id_raw = raw.get("template_id")
    if isinstance(template_id_raw, str) and template_id_raw.strip():
        template_id = template_id_raw.strip().lower()
    else:
        template_id = f"{kind_n}-v1"

    label: str | None = None
    lab_raw = raw.get("label")
    if isinstance(lab_raw, str) and lab_raw.strip():
        label = lab_raw.strip()

    description: str | None = None
    desc_raw = raw.get("description")
    if isinstance(desc_raw, str) and desc_raw.strip():
        description = desc_raw.strip()

    template: Path | None = None
    t_rel = raw.get("template")
    if isinstance(t_rel, str) and t_rel.strip():
        try:
            template = _safe_relative_file(bundle_dir, t_rel, "template")
        except ValueError as e:
            logger.warning("%s in %s", e, marker)
            template = None
        if template is not None and not template.is_file():
            logger.warning("template file missing: %s (%s)", template, marker)
            template = None

    schema_sql: Path | None = None
    s_rel = raw.get("schema_sql")
    if isinstance(s_rel, str) and s_rel.strip():
        try:
            schema_sql = _safe_relative_file(bundle_dir, s_rel, "schema_sql")
        except ValueError as e:
            logger.warning("%s in %s", e, marker)
            schema_sql = None
        if schema_sql is not None and not schema_sql.is_file():
            logger.warning("schema_sql file missing: %s (%s)", schema_sql, marker)
            schema_sql = None

    setup: Path | None = None
    u_rel = raw.get("setup")
    if isinstance(u_rel, str) and u_rel.strip():
        try:
            setup = _safe_relative_file(bundle_dir, u_rel, "setup")
        except ValueError as e:
            logger.warning("%s in %s", e, marker)
            setup = None
        if setup is not None and not setup.is_file():
            logger.warning("setup file missing: %s (%s)", setup, marker)
            setup = None

    return KindBundle(
        bundle_dir=bundle_dir,
        template_id=template_id,
        kind=kind_n,
        label=label,
        description=description,
        template=template,
        schema_sql=schema_sql,
        setup=setup,
    )


def iter_kind_bundles() -> Iterator[KindBundle]:
    root = dashboard_tree_root()
    if not root.is_dir():
        return
    seen_dirs: set[str] = set()
    for marker_name in _KIND_MARKERS:
        for marker in sorted(root.rglob(marker_name)):
            key = str(marker.parent.resolve())
            if key in seen_dirs:
                continue
            b = _parse_bundle(marker)
            if b is not None:
                seen_dirs.add(key)
                yield b


def bundles_by_kind() -> dict[str, KindBundle]:
    """First bundle per ``kind`` wins (paths sorted for stable order)."""
    out: dict[str, KindBundle] = {}
    for b in iter_kind_bundles():
        if b.kind in out:
            logger.warning(
                "duplicate kind %r — keeping %s, ignoring %s",
                b.kind,
                out[b.kind].bundle_dir,
                b.bundle_dir,
            )
            continue
        out[b.kind] = b
    return out


def bundles_by_template_id() -> dict[str, KindBundle]:
    """First bundle per ``template_id`` wins."""
    out: dict[str, KindBundle] = {}
    for b in iter_kind_bundles():
        if b.template_id in out:
            logger.warning(
                "duplicate template_id %r — keeping %s, ignoring %s",
                b.template_id,
                out[b.template_id].bundle_dir,
                b.bundle_dir,
            )
            continue
        out[b.template_id] = b
    return out


def _fallback_label(kind: str) -> str:
    k = (kind or "").strip().lower()
    if not k:
        return "Dashboard"
    return k.replace("_", " ").title()


def kind_catalog() -> list[dict[str, Any]]:
    """Legacy catalog keyed by ``kind`` — prefer ``template_catalog()``."""
    return template_catalog()


def template_catalog() -> list[dict[str, Any]]:
    """UI + API: one row per gallery template (``template_id`` primary key)."""
    rows: list[dict[str, Any]] = []
    for tid, b in sorted(bundles_by_template_id().items()):
        lab = (b.label or "").strip() if b.label else ""
        if not lab:
            lab = _fallback_label(b.kind)
        desc = (b.description or "").strip() if b.description else ""
        rows.append(
            {
                "template_id": tid,
                "kind": b.kind,
                "label": lab,
                "description": desc,
                "has_template": bool(b.template and b.template.is_file()),
                "has_schema": bool(b.schema_sql and b.schema_sql.is_file()),
                "has_setup": bool(b.setup and b.setup.is_file()),
            }
        )
    return rows


def template_path_for_template_id(template_id: str) -> Path | None:
    tid = (template_id or "").strip().lower()
    b = bundles_by_template_id().get(tid)
    if not b or not b.template:
        return None
    return b.template if b.template.is_file() else None


def template_path_for_kind(kind: str) -> Path | None:
    k = (kind or "").strip().lower()
    b = bundles_by_kind().get(k)
    if not b or not b.template:
        return None
    return b.template if b.template.is_file() else None


def kinds_with_schema_sql() -> list[str]:
    """Kinds whose bundle declares an on-disk ``schema_sql`` (install offers)."""
    return sorted(
        k for k, b in bundles_by_kind().items() if b.schema_sql and b.schema_sql.is_file()
    )


def kinds_with_templates() -> list[str]:
    """Legacy: kinds with on-disk layout templates."""
    return sorted(
        b.kind for b in bundles_by_template_id().values() if b.template and b.template.is_file()
    )


def template_ids_with_templates() -> list[str]:
    """Template ids that can be instantiated from gallery files."""
    return sorted(
        tid
        for tid, b in bundles_by_template_id().items()
        if b.template and b.template.is_file()
    )


def schema_sql_paths_for_kinds(kinds: list[str]) -> list[Path]:
    """SQL files for the given kinds only (unique paths, sorted)."""
    wanted = {x.strip().lower() for x in kinds if x and str(x).strip()}
    if not wanted:
        return []
    seen: set[str] = set()
    paths: list[Path] = []
    for k, b in bundles_by_kind().items():
        if k not in wanted:
            continue
        if not b.schema_sql or not b.schema_sql.is_file():
            continue
        key = str(b.schema_sql.resolve())
        if key in seen:
            continue
        seen.add(key)
        paths.append(b.schema_sql)
    paths.sort(key=lambda p: str(p))
    return paths
