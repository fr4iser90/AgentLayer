"""Load tool tools only from configured directories (``*.py`` files); no package hardcoding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

# Ensure apps.backend is in Python path for plugin imports
_backend_path = Path(__file__).parents[2] / "apps" / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from apps.backend.core.config import config
from apps.backend.infrastructure.db import db
from apps.backend.domain.plugin_system.capability_index import build_capability_index
from apps.backend.domain.plugin_system.tool_manifest_dimensions import (
    normalize_execution_context,
    normalize_min_role,
    normalize_risk_level,
    parse_allowed_tenant_ids,
    parse_os_support,
)
from apps.backend.domain.plugin_system.tool_ui_catalog import apply_tool_ui_metadata

logger = logging.getLogger(__name__)

# Admin UI grouping only; each module may set ``TOOL_BUCKET`` / ``TOOL_ADMIN_TAGS`` (plug-and-play).
_ALLOWED_ADMIN_BUCKETS = frozenset(
    {
        "files",
        "network",
        "knowledge",
        "secrets",
        "comms",
        "verticals",
        "meta",
        "media",
        "productivity",
        "unsorted",
    }
)


def _apply_admin_ui_metadata(mod: Any, entry: dict[str, Any]) -> None:
    """``admin_bucket`` / ``admin_tags`` from the tool module only (no central tool list)."""
    pid = str(entry.get("id") or "").strip()
    raw_b = getattr(mod, "TOOL_BUCKET", None)
    bucket = (
        str(raw_b).strip().lower()
        if isinstance(raw_b, str) and raw_b.strip()
        else "unsorted"
    )
    if bucket not in _ALLOWED_ADMIN_BUCKETS:
        logger.warning("unknown TOOL_BUCKET %r for %s — using unsorted", raw_b, pid)
        bucket = "unsorted"
    entry["admin_bucket"] = bucket

    at = getattr(mod, "TOOL_ADMIN_TAGS", None)
    if isinstance(at, (list, tuple, frozenset, set)):
        tags = [str(x).strip() for x in at if str(x).strip()]
        if tags:
            entry["admin_tags"] = tags
    elif isinstance(at, str) and at.strip():
        entry["admin_tags"] = [
            x.strip() for x in at.replace(";", ",").split(",") if x.strip()
        ]


class _RouterAccum:
    """Mutable state while scanning modules for router metadata (``TOOL_DOMAIN``, triggers, …)."""

    __slots__ = ("cat_TOOL_DESCRIPTION", "cat_TOOL_LABEL", "order", "tools", "TOOL_TRIGGERS")

    def __init__(self) -> None:
        self.tools: dict[str, set[str]] = {}
        self.TOOL_TRIGGERS: dict[str, set[str]] = {}
        self.order: list[str] = []
        self.cat_TOOL_LABEL: dict[str, str] = {}
        self.cat_TOOL_DESCRIPTION: dict[str, str] = {}

Handler = Callable[[dict[str, Any]], str]


def _apply_manifest_extras(mod: Any, entry: dict[str, Any]) -> None:
    """Optional module fields: execution_context, capabilities, secrets, min_role, tenant allowlist, families.

    ``TOOL_SECRETS_REQUIRED`` → ``secrets_required`` (user secret ``service_key`` names for Connections UI).
    ``TOOL_REQUIRES`` is handled earlier → ``requires`` only; do **not** merge into ``secrets_required``.
    """
    xctx = getattr(mod, "TOOL_EXECUTION_CONTEXT", None)
    entry["execution_context"] = normalize_execution_context(
        xctx if isinstance(xctx, str) else None
    )
    oss = parse_os_support(mod)
    if oss:
        entry["os_support"] = oss
    rlv = getattr(mod, "TOOL_RISK_LEVEL", None)
    nr = normalize_risk_level(rlv)
    if nr:
        entry["risk_level"] = nr

    caps = getattr(mod, "TOOL_CAPABILITIES", None)
    if isinstance(caps, (list, tuple, frozenset, set)):
        lc = [str(x).strip() for x in caps if str(x).strip()]
        if lc:
            entry["capabilities"] = lc
    req = getattr(mod, "TOOL_SECRETS_REQUIRED", None)
    if isinstance(req, (list, tuple, frozenset, set)):
        lr = [str(x).strip() for x in req if str(x).strip()]
        if lr:
            entry["secrets_required"] = lr
    mr = getattr(mod, "TOOL_MIN_ROLE", None)
    entry["min_role"] = normalize_min_role(mr if isinstance(mr, str) else None)
    at = getattr(mod, "TOOL_ALLOWED_TENANT_IDS", None)
    entry["allowed_tenant_ids"] = parse_allowed_tenant_ids(at)
    fam = getattr(mod, "TOOL_FAMILIES", None)
    if isinstance(fam, (list, tuple, frozenset, set)):
        lf = [str(x).strip() for x in fam if str(x).strip()]
        if lf:
            entry["families"] = lf
    # Optional: per ``service_key`` UI hints for Settings → Connections (fields + help text).
    usf = getattr(mod, "TOOL_USER_SECRET_FORMS", None)
    if isinstance(usf, dict) and usf:
        cleaned: dict[str, Any] = {}
        for k, v in usf.items():
            sk = str(k).strip().lower()
            if sk and isinstance(v, dict):
                cleaned[sk] = v
        if cleaned:
            entry["user_secret_forms"] = cleaned


def _path_under_or_equal(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _iter_tool_py_files(root: Path) -> list[Path]:
    """All ``*.py`` under ``root`` (recursive), excluding ``__init__.py``, ``_*``, ``__pycache__``."""
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        out.append(path)
    return out


def _stable_module_slug(directory: Path, path: Path, dir_idx: int) -> str:
    """Unique import-safe suffix for ``spec_from_file_location`` (avoids stem collisions across subdirs)."""
    try:
        rel = path.resolve().relative_to(directory.resolve())
    except (ValueError, OSError):
        rel = Path(path.name)
    rel_no_suffix = rel.with_suffix("")
    parts = [re.sub(r"[^a-zA-Z0-9_]", "_", str(p)) for p in rel_no_suffix.parts]
    slug = "_".join(p for p in parts if p).strip("_") or "tool"
    if slug and slug[0].isdigit():
        slug = f"m_{slug}"
    return f"{dir_idx}_{slug}"


class ToolRegistry:
    """Scans ``AGENT_TOOL_DIRS`` or default ``tools`` + optional extra mount."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._handlers: dict[str, Handler] = {}
        self._chat_tool_specs: list[dict[str, Any]] = []
        self._tools_meta: list[dict[str, Any]] = []
        self._router_cat_tools: dict[str, frozenset[str]] = {}
        self._router_cat_TOOL_TRIGGERS: dict[str, frozenset[str]] = {}
        self._router_cat_order: list[str] = []
        self._router_cat_TOOL_LABEL: dict[str, str] = {}
        self._router_cat_TOOL_DESCRIPTION: dict[str, str] = {}
        self._capability_index: dict[str, list[dict[str, Any]]] = {}
        self._tool_step_detail_fns: dict[str, Any] = {}

    def load_all(self) -> None:
        with self._lock:
            self._clear_storage()
            self._purge_dynamic_tool_modules()
            acc_h: dict[str, Handler] = {}
            acc_tools: list[dict[str, Any]] = []
            acc_meta: list[dict[str, Any]] = []
            acc_step_detail: dict[str, Any] = {}
            router = _RouterAccum()
            scan_stats: dict[str, int] = {"cron_skipped": 0}

            allow = config.tools_allowed_sha256()
            extra_raw = (config.TOOLS_EXTRA_DIR or "").strip()
            extra_root: Path | None = None
            if extra_raw:
                try:
                    extra_root = Path(extra_raw).expanduser().resolve()
                except OSError:
                    extra_root = Path(extra_raw).expanduser()

            dirs = config.tool_scan_directories()
            if not dirs:
                logger.warning("no tool directories to scan (set AGENT_TOOL_DIRS or ship tools)")

            for dir_idx, directory in enumerate(dirs):
                if not directory.is_dir():
                    logger.warning("skip missing tool directory: %s", directory)
                    continue
                for path in _iter_tool_py_files(directory):
                    try:
                        data = path.read_bytes()
                    except OSError:
                        logger.exception("cannot read tool file %s", path)
                        continue
                    digest = hashlib.sha256(data).hexdigest()
                    try:
                        path_r = path.resolve()
                    except OSError:
                        path_r = path
                    needs_sha = (
                        allow is not None
                        and extra_root is not None
                        and extra_root.is_dir()
                        and _path_under_or_equal(path_r, extra_root)
                    )
                    if needs_sha and digest not in allow:
                        logger.error(
                            "rejecting tool (not in AGENT_TOOLS_ALLOWED_SHA256): %s",
                            path,
                        )
                        continue
                    slug = _stable_module_slug(directory, path, dir_idx)
                    mod_name = f"agent_tool_{slug}"
                    try:
                        spec = importlib.util.spec_from_file_location(mod_name, path)
                        if spec is None or spec.loader is None:
                            logger.error("cannot load tool spec: %s", path)
                            continue
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_name] = mod
                        spec.loader.exec_module(mod)
                    except Exception:
                        logger.exception("failed to load tool %s", path)
                        continue
                    self._register_module(
                        mod,
                        source=f"file:{path}",
                        handlers=acc_h,
                        tools=acc_tools,
                        meta=acc_meta,
                        step_detail_fns=acc_step_detail,
                        file_sha256=digest,
                        router=router,
                        scan_stats=scan_stats,
                    )

            logger.info(
                "tool registry: %d packages, %d tool names, %d cron-only modules skipped "
                "(per-package lines: DEBUG)",
                len(acc_meta),
                len(acc_h),
                scan_stats.get("cron_skipped", 0),
            )

            self._handlers = acc_h
            self._chat_tool_specs = acc_tools
            self._tools_meta = acc_meta
            self._tool_step_detail_fns = dict(acc_step_detail)
            self._router_cat_tools = {k: frozenset(v) for k, v in router.tools.items()}
            self._router_cat_TOOL_TRIGGERS = {k: frozenset(v) for k, v in router.TOOL_TRIGGERS.items()}
            self._router_cat_order = list(router.order)
            self._router_cat_TOOL_LABEL = dict(router.cat_TOOL_LABEL)
            self._router_cat_TOOL_DESCRIPTION = dict(router.cat_TOOL_DESCRIPTION)
            self._capability_index = build_capability_index(acc_meta)

    def _clear_storage(self) -> None:
        self._handlers.clear()
        self._chat_tool_specs.clear()
        self._tools_meta.clear()
        self._router_cat_tools = {}
        self._router_cat_TOOL_TRIGGERS = {}
        self._router_cat_order = []
        self._router_cat_TOOL_LABEL = {}
        self._router_cat_TOOL_DESCRIPTION = {}
        self._capability_index = {}
        self._tool_step_detail_fns = {}

    def _purge_dynamic_tool_modules(self) -> None:
        for key in list(sys.modules):
            if key.startswith("agent_tool_"):
                del sys.modules[key]

    def _register_module(
        self,
        mod: Any,
        source: str,
        handlers: dict[str, Handler],
        tools: list[dict[str, Any]],
        meta: list[dict[str, Any]],
        *,
        step_detail_fns: dict[str, Any] | None = None,
        file_sha256: str | None = None,
        router: _RouterAccum | None = None,
        scan_stats: dict[str, int] | None = None,
    ) -> None:
        mod_tools = getattr(mod, "TOOLS", None)
        mod_handlers = getattr(mod, "HANDLERS", None)
        if mod_tools is None and mod_handlers is None:
            return
        if mod_handlers is None:
            return
        if mod_tools is None:
            mod_tools = []
        if not isinstance(mod_tools, list) or not isinstance(mod_handlers, dict):
            logger.error(
                "invalid tool exports (need TOOLS list and HANDLERS dict): %s", source
            )
            return

        pid = getattr(mod, "TOOL_ID", None) or getattr(mod, "__name__", "unknown")
        ver = str(getattr(mod, "__version__", "0"))
        tool_names: list[str] = []
        pending_handlers: dict[str, Handler] = {}
        pending_specs: list[dict[str, Any]] = []

        dom_raw = getattr(mod, "TOOL_DOMAIN", None)
        dom = dom_raw.strip().lower() if isinstance(dom_raw, str) and dom_raw.strip() else ""

        for spec in mod_tools:
            if not isinstance(spec, dict):
                continue
            fn = spec.get("function") or {}
            name = fn.get("name")
            if not name:
                logger.warning("skip tool without name in %s", source)
                continue
            handler = mod_handlers.get(name)
            if not callable(handler):
                logger.error(
                    "skip tool %r in %s: no callable handler in HANDLERS",
                    name,
                    source,
                )
                continue
            registered = str(name)
            if registered in handlers or registered in pending_handlers:
                if dom:
                    qualified = f"{dom}.{registered}"
                    if qualified not in handlers and qualified not in pending_handlers:
                        registered = qualified
                    else:
                        logger.warning(
                            "skip tool %r in %s: name collision (%s already registered)",
                            name,
                            source,
                            registered,
                        )
                        continue
                else:
                    logger.warning(
                        "skip tool %r in %s: name collision (no TOOL_DOMAIN to qualify)",
                        name,
                        source,
                    )
                    continue
            spec_out = spec
            if registered != name:
                spec_out = json.loads(json.dumps(spec))
                fn_out = spec_out.get("function")
                if isinstance(fn_out, dict):
                    fn_out["name"] = registered
            pending_handlers[registered] = handler  # type: ignore[assignment]
            pending_specs.append(spec_out)
            tool_names.append(registered)

        handlers.update(pending_handlers)
        tools.extend(pending_specs)

        _detail_by_name = getattr(mod, "TOOL_STEP_DETAIL_BY_NAME", None)
        _mod_detail_fn = getattr(mod, "tool_step_detail", None)
        if step_detail_fns is not None:
            for tn in tool_names:
                fn = None
                if isinstance(_detail_by_name, dict):
                    cand = _detail_by_name.get(tn)
                    if callable(cand):
                        fn = cand
                if fn is None and callable(_mod_detail_fn):
                    fn = _mod_detail_fn
                if fn is not None:
                    step_detail_fns[tn] = fn

        if not tool_names:
            # HANDLERS present but no TOOLS → cron-only module; scheduled_job_registry may pick it up
            if scan_stats is not None:
                scan_stats["cron_skipped"] = scan_stats.get("cron_skipped", 0) + 1
            logger.debug(
                "skipping cron-only module %s v%s (%d HANDLERS keys, no TOOLS) — not in tool registry",
                pid,
                ver,
                len(mod_handlers),
            )
            return

        for declared in mod_handlers:
            if declared not in tool_names:
                logger.warning(
                    "tool %s declares handler %r without matching TOOLS entry",
                    source,
                    declared,
                )

        entry: dict[str, Any] = {
            "id": pid,
            "version": ver,
            "source": source,
            "tools": tool_names,
        }
        if file_sha256 is not None:
            entry["sha256"] = file_sha256
        tags = getattr(mod, "TOOL_TAGS", None)
        if isinstance(tags, (list, tuple, frozenset, set)):
            tl = [str(x).strip() for x in tags if str(x).strip()]
            if tl:
                entry["tags"] = tl
        elif isinstance(tags, str) and tags.strip():
            entry["tags"] = [
                x.strip() for x in tags.replace(";", ",").split(",") if x.strip()
            ]
        dom = getattr(mod, "TOOL_DOMAIN", None)
        if isinstance(dom, str) and dom.strip():
            entry["domain"] = dom.strip().lower()
        prov = getattr(mod, "TOOL_PROVIDER", None)
        if isinstance(prov, str) and prov.strip():
            entry["provider"] = prov.strip().lower()
        # Declared context / argument hints (e.g. domain tools). Not user secret keys — use TOOL_SECRETS_REQUIRED.
        req = getattr(mod, "TOOL_REQUIRES", None)
        if isinstance(req, (list, tuple, frozenset, set)):
            rl = [str(x).strip() for x in req if str(x).strip()]
            if rl:
                entry["requires"] = rl
        ptm = getattr(mod, "AGENT_TOOL_META_BY_NAME", None)
        if isinstance(ptm, dict) and ptm:
            per: dict[str, Any] = {}
            for k, v in ptm.items():
                if not isinstance(v, dict):
                    continue
                nk = str(k).strip()
                if not nk:
                    continue
                row: dict[str, Any] = {}
                r_req = v.get("requires")
                r_sec = v.get("secrets_required")
                if isinstance(r_req, (list, tuple)):
                    lr = [str(x).strip() for x in r_req if str(x).strip()]
                    if lr:
                        row["requires"] = lr
                if isinstance(r_sec, (list, tuple)):
                    ls = [str(x).strip() for x in r_sec if str(x).strip()]
                    if ls:
                        row["secrets_required"] = ls
                t2 = v.get("tags")
                if isinstance(t2, (list, tuple)):
                    lt = [str(x).strip() for x in t2 if str(x).strip()]
                    if lt:
                        row["tags"] = lt
                c2 = v.get("capabilities")
                if isinstance(c2, (list, tuple)):
                    lc = [str(x).strip() for x in c2 if str(x).strip()]
                    if lc:
                        row["capabilities"] = lc
                if isinstance(v.get("min_role"), str):
                    row["min_role"] = normalize_min_role(v["min_role"])
                if "allowed_tenant_ids" in v:
                    row["allowed_tenant_ids"] = parse_allowed_tenant_ids(v.get("allowed_tenant_ids"))
                if isinstance(v.get("execution_context"), str):
                    row["execution_context"] = normalize_execution_context(v["execution_context"])
                if isinstance(v.get("os_support"), (list, tuple)):
                    row["os_support"] = [str(x).strip().lower() for x in v["os_support"] if str(x).strip()]
                if v.get("risk_level") is not None:
                    nr = normalize_risk_level(v.get("risk_level"))
                    if nr:
                        row["risk_level"] = nr
                if row:
                    per[nk] = row
            if per:
                entry["per_tool"] = per
        _apply_manifest_extras(mod, entry)
        _apply_admin_ui_metadata(mod, entry)
        apply_tool_ui_metadata(mod, entry)
        meta.append(entry)
        logger.debug(
            "loaded tool %s v%s (%d tools) [%s]", pid, ver, len(tool_names), source
        )

        if router is not None and tool_names:
            rcat = getattr(mod, "TOOL_DOMAIN", None)
            if isinstance(rcat, str) and rcat.strip():
                key = rcat.strip().lower()
                if key not in router.order:
                    router.order.append(key)
                router.tools.setdefault(key, set()).update(tool_names)
                if key not in router.cat_TOOL_LABEL:
                    lab = getattr(mod, "TOOL_LABEL", None)
                    if isinstance(lab, str) and lab.strip():
                        router.cat_TOOL_LABEL[key] = lab.strip()
                if key not in router.cat_TOOL_DESCRIPTION:
                    cdesc = getattr(mod, "TOOL_DESCRIPTION", None)
                    if isinstance(cdesc, str) and cdesc.strip():
                        router.cat_TOOL_DESCRIPTION[key] = cdesc.strip()
                if "TOOL_TRIGGERS" in mod.__dict__:
                    tr = mod.TOOL_TRIGGERS
                    parts: list[str] = []
                    if isinstance(tr, str):
                        parts = [
                            x.strip().lower()
                            for x in tr.replace(";", ",").split(",")
                            if x.strip()
                        ]
                    elif isinstance(tr, (list, tuple, frozenset, set)):
                        parts = [str(x).strip().lower() for x in tr if str(x).strip()]
                    if parts:
                        router.TOOL_TRIGGERS.setdefault(key, set()).update(parts)
                else:
                    tid = str(pid).strip().lower()
                    if tid:
                        router.TOOL_TRIGGERS.setdefault(key, set()).add(tid)

    def router_tool_names_for_category(self, category: str) -> frozenset[str]:
        with self._lock:
            return self._router_cat_tools.get(category.strip().lower(), frozenset())

    def domain_trigger_substrings(self, domain: str) -> tuple[str, ...]:
        """Module-level ``TOOL_TRIGGERS`` substrings for a ``TOOL_DOMAIN`` (lowercase)."""
        key = (domain or "").strip().lower()
        if not key:
            return ()
        with self._lock:
            raw = self._router_cat_TOOL_TRIGGERS.get(key, frozenset())
        return tuple(sorted(str(x).strip().lower() for x in raw if str(x).strip()))

    def _router_category_order(self) -> list[str]:
        """Call with ``self._lock`` held."""
        known = frozenset(self._router_cat_tools.keys())
        order: list[str] = []
        seen: set[str] = set()
        for c in config.AGENT_TOOL_DOMAIN_ORDER:
            if c in known and c not in seen:
                order.append(c)
                seen.add(c)
        for c in self._router_cat_order:
            if c in known and c not in seen:
                order.append(c)
                seen.add(c)
        return order

    def list_router_categories_catalog(self) -> list[dict[str, Any]]:
        """Category ids with optional TOOL_LABEL/TOOL_DESCRIPTION from modules; tool counts only (no schemas)."""
        with self._lock:
            order = self._router_category_order()
            out: list[dict[str, Any]] = []
            for cid in order:
                tools = self._router_cat_tools.get(cid)
                if not tools:
                    continue
                TOOL_LABEL = self._router_cat_TOOL_LABEL.get(cid) or cid
                desc = self._router_cat_TOOL_DESCRIPTION.get(cid) or ""
                out.append(
                    {
                        "id": cid,
                        "TOOL_LABEL": TOOL_LABEL,
                        "TOOL_DESCRIPTION": desc,
                        "tool_count": len(tools),
                    }
                )
            return out

    def list_router_category_tools_lite(self, category: str) -> list[dict[str, str]]:
        """Registered tool function names + TOOL_DESCRIPTIONs for one router category; no parameter schemas."""
        c = category.strip().lower()
        with self._lock:
            names = self._router_cat_tools.get(c)
            if not names:
                return []
            name_set = set(names)
            rows: list[dict[str, str]] = []
            for spec in self._chat_tool_specs:
                fn = spec.get("function") if isinstance(spec, dict) else None
                if not isinstance(fn, dict):
                    continue
                n = fn.get("name")
                if not n or n not in name_set:
                    continue
                rows.append(
                    {
                        "name": str(n),
                        "TOOL_DESCRIPTION": (fn.get("TOOL_DESCRIPTION") or "").strip(),
                    }
                )
        rows.sort(key=lambda r: r["name"])
        return rows

    def classify_tool_router_categories(self, user_text: str) -> frozenset[str]:
        """Every category whose trigger set matches ``user_text`` (substring, lowercased)."""
        if not (user_text or "").strip():
            return frozenset()
        tl = user_text.lower()
        with self._lock:
            order = self._router_category_order()
            TOOL_TRIGGERS_map = self._router_cat_TOOL_TRIGGERS
        matched: set[str] = set()
        for cat in order:
            for sub in TOOL_TRIGGERS_map.get(cat, frozenset()):
                if sub and sub in tl:
                    matched.add(cat)
                    break
        return frozenset(matched)

    def classify_tool_router_category(self, user_text: str) -> str | None:
        """First matching category in router order (legacy single-winner)."""
        cats = self.classify_tool_router_categories(user_text)
        if not cats:
            return None
        with self._lock:
            order = self._router_category_order()
        for c in order:
            if c in cats:
                return c
        return next(iter(cats))

    @property
    def chat_tool_specs(self) -> list[dict[str, Any]]:
        """Specs in Chat Completions ``tools[]`` shape (HTTP wire format only; tools are yours)."""
        with self._lock:
            return list(self._chat_tool_specs)

    @property
    def tools_meta(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._tools_meta)

    @property
    def capability_index(self) -> dict[str, list[dict[str, Any]]]:
        """Inverted capability → handlers index (see ADR 0001)."""
        with self._lock:
            return dict(self._capability_index)

    def meta_entry_for_tool_name(self, registered_function_name: str) -> dict[str, Any] | None:
        """
        First ``tools_meta`` row whose ``tools`` list contains this registered function ``name``
        (same scan order as load; use when exposing module path to ``get_tool_help``).
        """
        n = (registered_function_name or "").strip()
        if not n:
            return None
        with self._lock:
            for entry in self._tools_meta:
                tlist = entry.get("tools")
                if isinstance(tlist, list) and n in tlist:
                    return dict(entry)
        return None

    def display_label_for_tool(self, registered_function_name: str) -> str | None:
        """User-facing label from plugin ``TOOL_UI`` / ``TOOL_LABEL`` (not hard-coded in chat UI)."""
        entry = self.meta_entry_for_tool_name(registered_function_name)
        if not entry:
            return None
        ui = entry.get("ui")
        if isinstance(ui, dict):
            dn = ui.get("display_name")
            if isinstance(dn, str) and dn.strip():
                return dn.strip()
        return None

    def tool_step_detail_for(self, registered_function_name: str, arguments: dict[str, Any]) -> str:
        """Call plugin ``tool_step_detail`` when registered for this tool name."""
        n = (registered_function_name or "").strip()
        if not n:
            return ""
        with self._lock:
            fn = self._tool_step_detail_fns.get(n)
        if not callable(fn):
            return ""
        try:
            out = fn(dict(arguments or {}))
        except Exception:
            logger.debug("tool_step_detail failed for %r", n, exc_info=True)
            return ""
        if out is None:
            return ""
        return str(out).strip()

    def resolve_domain_tool(self, domain: str, base_name: str) -> str | None:
        """Registered name for ``domain`` + ``base_name`` (``domain.base`` or bare ``base`` if unique)."""
        dom = (domain or "").strip().lower()
        base = (base_name or "").strip()
        if not base:
            return None
        qualified = f"{dom}.{base}" if dom else base
        with self._lock:
            if qualified in self._handlers:
                return qualified
            if base in self._handlers:
                entry = self.meta_entry_for_tool_name(base)
                if entry and str(entry.get("domain") or "").lower() == dom:
                    return base
        return None

    def tool_names_for_capabilities(self, *capabilities: str) -> list[str]:
        """Registered tool function names declaring any of ``capabilities``."""
        want = {str(c).strip() for c in capabilities if str(c).strip()}
        if not want:
            return []
        out: list[str] = []
        with self._lock:
            for entry in self._tools_meta:
                tlist = entry.get("tools")
                if not isinstance(tlist, list):
                    continue
                per = entry.get("per_tool") if isinstance(entry.get("per_tool"), dict) else {}
                mod_caps = entry.get("capabilities")
                mod_cap_set = (
                    {str(x).strip() for x in mod_caps if str(x).strip()}
                    if isinstance(mod_caps, list)
                    else set()
                )
                for tn in tlist:
                    n = str(tn).strip()
                    if not n:
                        continue
                    caps: set[str] = set(mod_cap_set)
                    row = per.get(n) if isinstance(per, dict) else None
                    if isinstance(row, dict):
                        rc = row.get("capabilities")
                        if isinstance(rc, list):
                            caps.update(str(x).strip() for x in rc if str(x).strip())
                    if caps & want and n not in out:
                        out.append(n)
        return out

    def run_tool(self, name: str, arguments: dict[str, Any], context: dict | None = None) -> str:
        with self._lock:
            handler = self._handlers.get(name)
        if not handler:
            return json.dumps({"ok": False, "error": f"unknown tool: {name}"})
        ok = True
        try:
            # Check if handler supports context parameter
            import inspect
            sig = inspect.signature(handler) if hasattr(handler, '__call__') else None
            if sig and 'context' in sig.parameters:
                out = handler(dict(arguments or {}), context=context)
            else:
                # Backward compatibility - call without context
                out = handler(dict(arguments or {}))
            payload = json.loads(out) if out else {}
            if isinstance(payload, dict) and payload.get("ok") is False:
                ok = False
        except Exception as e:
            ok = False
            out = json.dumps({"ok": False, "error": str(e)})
        from apps.backend.domain.tool_invocation_context import get_agent_run_id

        rid = get_agent_run_id()
        db.log_tool_invocation(
            name, dict(arguments or {}), out, ok, agent_run_id=rid
        )
        return out


_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ToolRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ToolRegistry()
            _registry.load_all()
        return _registry


def reload_registry(scope: str = "all") -> ToolRegistry:
    """Full rescan of tool directories. ``scope`` is kept for API compatibility only."""
    global _registry
    s = (scope or "all").strip().lower()
    if s not in ("all", "extra"):
        raise ValueError("scope must be 'all' or 'extra'")

    with _registry_lock:
        candidate = ToolRegistry()
        candidate.load_all()
        _registry = candidate
        return _registry
