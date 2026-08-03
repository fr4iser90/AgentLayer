"""Full LSP (Language Server Protocol) client with proper JSON-RPC over stdio.

Matches coding's architecture:
- Content-Length framed JSON-RPC messages
- Initialize handshake with capability negotiation
- Document synchronization (didOpen, didChange, didSave, willSave)
- Push/pull diagnostics with debounce
- Multi-server support per language
- Server lifecycle management (start, restart, stop)
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from apps.backend.infrastructure.platform.config import config

logger = logging.getLogger(__name__)

_CONTENT_LENGTH_RE = re.compile(r"Content-Length:\s*(\d+)", re.IGNORECASE)

ROOT_MARKERS: dict[str, tuple[str, ...]] = {
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "pyrightconfig.json"),
    "go": ("go.mod", "go.work"),
    "rust": ("Cargo.toml",),
    "typescript": ("package.json", "tsconfig.json", "jsconfig.json"),
    "javascript": ("package.json", "jsconfig.json"),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "ruby": ("Gemfile",),
    "php": ("composer.json",),
    "csharp": ("*.csproj", "*.sln"),
    "dart": ("pubspec.yaml",),
    "elixir": ("mix.exs",),
    "haskell": ("package.yaml", "stack.yaml", "cabal.project"),
    "lua": (".luarc.json",),
    "terraform": (".terraform", "*.tf"),
    "sql": ("*.sql",),
}


class Language(str, Enum):
    PYTHON = "python"
    GO = "go"
    RUST = "rust"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    RUBY = "ruby"
    PHP = "php"
    CSHARP = "csharp"
    DART = "dart"
    ELIXIR = "elixir"
    HASKELL = "haskell"
    LUA = "lua"
    TERRAFORM = "terraform"
    SQL = "sql"


LANGUAGE_EXTENSIONS: dict[Language, tuple[str, ...]] = {
    Language.PYTHON: ("py", "pyi"),
    Language.GO: ("go",),
    Language.RUST: ("rs",),
    Language.TYPESCRIPT: ("ts", "tsx", "mts", "cts"),
    Language.JAVASCRIPT: ("js", "jsx", "mjs", "cjs"),
    Language.JAVA: ("java",),
    Language.RUBY: ("rb",),
    Language.PHP: ("php",),
    Language.CSHARP: ("cs",),
    Language.DART: ("dart",),
    Language.ELIXIR: ("ex", "exs"),
    Language.HASKELL: ("hs", "lhs"),
    Language.LUA: ("lua",),
    Language.TERRAFORM: ("tf", "tfvars"),
    Language.SQL: ("sql",),
}

LANGUAGE_SERVERS: dict[Language, dict[str, Any]] = {
    Language.PYTHON: {
        "command": ["pyright-langserver", "--stdio"],
        "alternatives": [
            ["pylsp", "--stdio"],
            ["jedi-language-server", "--stdio"],
        ],
    },
    Language.GO: {
        "command": ["gopls"],
        "alternatives": [],
    },
    Language.RUST: {
        "command": ["rust-analyzer"],
        "alternatives": [],
    },
    Language.TYPESCRIPT: {
        "command": ["typescript-language-server", "--stdio"],
        "alternatives": [
            ["tsserver"],
            ["deno", "lsp"],
        ],
    },
    Language.JAVASCRIPT: {
        "command": ["typescript-language-server", "--stdio"],
        "alternatives": [
            ["deno", "lsp"],
        ],
    },
    Language.JAVA: {
        "command": ["jdtls"],
        "alternatives": [],
    },
    Language.RUBY: {
        "command": ["solargraph", "stdio"],
        "alternatives": [
            ["ruby-lsp", "stdio"],
        ],
    },
    Language.PHP: {
        "command": ["intelephense", "--stdio"],
        "alternatives": [
            ["phpactor", "language-server"],
        ],
    },
    Language.CSHARP: {
        "command": ["omnisharp", "--languageserver"],
        "alternatives": [],
    },
    Language.DART: {
        "command": ["dart", "language-server", "--protocol=lsp"],
        "alternatives": [],
    },
    Language.ELIXIR: {
        "command": ["elixir-ls"],
        "alternatives": [],
    },
    Language.HASKELL: {
        "command": ["haskell-language-server-wrapper", "--lsp"],
        "alternatives": [],
    },
    Language.LUA: {
        "command": ["lua-language-server"],
        "alternatives": [],
    },
    Language.TERRAFORM: {
        "command": ["terraform-ls", "serve"],
        "alternatives": [],
    },
    Language.SQL: {
        "command": ["sql-language-server", "up", "--method", "stdio"],
        "alternatives": [],
    },
}

# LSP DiagnosticSeverity → label for tool JSON (1=Error … 4=Hint).
_SEVERITY_LABELS: dict[int, str] = {
    1: "error",
    2: "warning",
    3: "information",
    4: "hint",
}
_SEVERITY_RANK: dict[str, int] = {
    "error": 0,
    "warning": 1,
    "information": 2,
    "hint": 3,
    "unknown": 4,
}


def _tried_server_bins(language: Language) -> list[str]:
    cfg = LANGUAGE_SERVERS.get(language, {})
    bins: list[str] = []
    primary = cfg.get("command") or []
    if primary:
        bins.append(str(primary[0]))
    for alt in cfg.get("alternatives") or []:
        if alt:
            bins.append(str(alt[0]))
    return bins


def _uri_to_workspace_path(uri: str, workspace_root: Path | None) -> str:
    path = _uri_to_path(uri)
    if path is None:
        return uri
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    if workspace_root is not None:
        try:
            return str(resolved.relative_to(workspace_root.resolve()))
        except ValueError:
            pass
    return str(resolved)


def format_one_diagnostic(
    raw: dict[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    """Normalize one LSP diagnostic into model-friendly 1-based locations."""
    severity_raw = raw.get("severity", 1)
    try:
        severity_n = int(severity_raw)
    except (TypeError, ValueError):
        severity_n = 1
    severity = _SEVERITY_LABELS.get(severity_n, "unknown")
    rng = raw.get("range") or {}
    start = rng.get("start") or {}
    end = rng.get("end") or {}
    try:
        line = int(start.get("line", 0)) + 1
    except (TypeError, ValueError):
        line = 1
    try:
        character = int(start.get("character", 0)) + 1
    except (TypeError, ValueError):
        character = 1
    try:
        end_line = int(end.get("line", start.get("line", 0))) + 1
    except (TypeError, ValueError):
        end_line = line
    try:
        end_character = int(end.get("character", start.get("character", 0))) + 1
    except (TypeError, ValueError):
        end_character = character
    code = raw.get("code")
    if isinstance(code, dict):
        code = code.get("value")
    item: dict[str, Any] = {
        "path": path,
        "severity": severity,
        "line": line,
        "character": character,
        "end_line": end_line,
        "end_character": end_character,
        "message": str(raw.get("message") or "")[:500],
    }
    if code is not None and str(code).strip():
        item["code"] = str(code)[:64]
    source = raw.get("source")
    if source:
        item["source"] = str(source)[:64]
    return item


def format_diagnostics_payload(
    raw_by_uri: dict[str, list[dict[str, Any]]],
    *,
    workspace_root: Path | None,
    requested_path: str | None = None,
    language: str | None = None,
    server_command: list[str] | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Build tool JSON with summary + capped, sorted diagnostics (errors first)."""
    cap = max_items if max_items is not None else int(getattr(config, "AGENT_LSP_DIAGNOSTICS_MAX", 40))
    items: list[dict[str, Any]] = []
    for uri, diags in (raw_by_uri or {}).items():
        rel = _uri_to_workspace_path(uri, workspace_root)
        for d in diags or []:
            if isinstance(d, dict):
                items.append(format_one_diagnostic(d, path=rel))
    items.sort(
        key=lambda d: (
            _SEVERITY_RANK.get(str(d.get("severity")), 4),
            str(d.get("path") or ""),
            int(d.get("line") or 0),
            int(d.get("character") or 0),
        )
    )
    summary = {"error": 0, "warning": 0, "information": 0, "hint": 0, "unknown": 0, "total": len(items)}
    for d in items:
        key = str(d.get("severity") or "unknown")
        if key not in summary:
            key = "unknown"
        summary[key] = int(summary[key]) + 1
    truncated = len(items) > cap
    shown = items[:cap]
    payload: dict[str, Any] = {
        "ok": True,
        "operation": "diagnostics",
        "path": requested_path,
        "language": language,
        "summary": summary,
        "diagnostics": shown,
    }
    if server_command:
        payload["server"] = server_command
    if truncated:
        payload["truncated"] = True
        payload["truncation_hint"] = (
            f"Showing {cap} of {summary['total']} diagnostics (errors first). "
            "Fix top errors, re-run with wait=true, or narrow to one path."
        )
    if summary["error"] > 0:
        payload["hint"] = (
            "Fix diagnostic errors before claiming the change is done; "
            "use apply_patch / edit on the cited path:line locations."
        )
    elif summary["total"] == 0:
        payload["hint"] = (
            "No diagnostics published for this file. "
            "If that seems wrong, call operation=status or restart, then diagnostics with wait=true."
        )
    else:
        payload["hint"] = "No errors; review warnings if they touch your change."
    return payload


def _find_workspace_root(file_path: Path, language: Language) -> Path | None:
    markers = ROOT_MARKERS.get(language.value, ())
    if not markers:
        return config.CODING_ROOT

    for parent in file_path.parents:
        for marker in markers:
            if "*" in marker or "?" in marker:
                if any(parent.glob(marker)):
                    return parent
            else:
                if (parent / marker).exists():
                    return parent

    if config.CODING_ROOT:
        return config.CODING_ROOT.resolve()
    return file_path.parent.resolve()


def _resolve_root(root_hint: Path | str | None, file_path: Path, language: Language) -> Path:
    if root_hint and isinstance(root_hint, Path):
        return root_hint.resolve()
    if root_hint and isinstance(root_hint, str):
        return Path(root_hint).resolve()
    found = _find_workspace_root(file_path, language)
    if found:
        return found
    return (config.CODING_ROOT or file_path.parent).resolve()


@dataclass
class DocumentInfo:
    uri: str
    version: int = 1
    content: str = ""
    language_id: str = ""


@dataclass
class DiagnosticInfo:
    uri: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    version: int = -1


class LSPServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    INITIALIZED = "initialized"
    STOPPING = "stopping"
    FAILED = "failed"


class LSPClient:
    def __init__(
        self,
        language: Language,
        root_path: Path | None = None,
        server_cmd: list[str] | None = None,
        diagnostics_debounce_ms: int = 150,
        diagnostics_timeout_s: int = 10,
    ):
        self.language = language
        self.root_path = root_path
        self.diagnostics_debounce_ms = diagnostics_debounce_ms
        self.diagnostics_timeout_s = diagnostics_timeout_s
        self.state = LSPServerState.STOPPED
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._request_id_lock = threading.Lock()
        self._pending_requests: dict[int, threading.Event] = {}
        self._responses: dict[int, dict[str, Any]] = {}
        self._response_lock = threading.Lock()
        self._documents: dict[str, DocumentInfo] = {}
        self._diagnostics: dict[str, DiagnosticInfo] = {}
        self._diagnostics_lock = threading.Lock()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._file_watcher: WorkspaceFileWatcher | None = None
        self._capabilities: dict[str, Any] = {}
        self._on_diagnostics_callbacks: list[Callable[[str, list[dict[str, Any]]], None]] = []
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._init_error: str | None = None
        self._start_lock = threading.Lock()
        override = None
        if server_cmd is None:
            try:
                override = config.lsp_server_cmd_override(language.value)
            except Exception:
                override = None
        self._command = server_cmd or override or LANGUAGE_SERVERS.get(language, {}).get("command", [])
        try:
            self.diagnostics_timeout_s = int(
                getattr(config, "AGENT_LSP_DIAGNOSTICS_TIMEOUT_SEC", diagnostics_timeout_s)
            )
        except Exception:
            self.diagnostics_timeout_s = diagnostics_timeout_s

    @property
    def is_alive(self) -> bool:
        return (
            self._process is not None
            and self._process.poll() is None
            and self.state in (LSPServerState.RUNNING, LSPServerState.INITIALIZED)
        )

    def on_diagnostics(self, callback: Callable[[str, list[dict[str, Any]]], None]) -> None:
        self._on_diagnostics_callbacks.append(callback)

    def start(self) -> bool:
        with self._start_lock:
            if self.is_alive:
                return True
            if self.state == LSPServerState.STARTING:
                return False
            return self._start()

    def _start(self) -> bool:
        if not self._command:
            self._init_error = f"No server command configured for language {self.language.value}"
            self.state = LSPServerState.FAILED
            logger.error("LSP %s: %s", self.language.value, self._init_error)
            return False

        cmd = self._command[0]
        if not _which(cmd):
            alternatives = LANGUAGE_SERVERS.get(self.language, {}).get("alternatives", [])
            for alt in alternatives:
                if _which(alt[0]):
                    self._command = alt
                    break
            else:
                tried = ", ".join(_tried_server_bins(self.language)) or cmd
                env_key = f"AGENT_LSP_{self.language.value.upper()}_CMD"
                self._init_error = (
                    f"LSP server for {self.language.value} not found in PATH "
                    f"(tried: {tried}). Install one or set {env_key}. "
                    f"See docs/runbooks/lsp.md."
                )
                self.state = LSPServerState.FAILED
                logger.error("LSP %s: %s", self.language.value, self._init_error)
                return False

        cwd = str(self.root_path) if self.root_path else None
        try:
            logger.info("LSP %s: starting %s in %s", self.language.value, self._command, cwd)
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                bufsize=0,
            )
            self.state = LSPServerState.STARTING
            self._stdout_thread = threading.Thread(
                target=self._read_stdout, name=f"lsp-{self.language.value}-stdout", daemon=True
            )
            self._stderr_thread = threading.Thread(
                target=self._read_stderr, name=f"lsp-{self.language.value}-stderr", daemon=True
            )
            self._stdout_thread.start()
            self._stderr_thread.start()
            return self._initialize()
        except Exception as e:
            self._init_error = f"Failed to start LSP server: {e}"
            self.state = LSPServerState.FAILED
            logger.error("LSP %s: %s", self.language.value, self._init_error)
            return False

    def _initialize(self) -> bool:
        try:
            root_uri = (
                self.root_path.as_uri() if self.root_path
                else (config.CODING_ROOT.as_uri() if config.CODING_ROOT else None)
            )
            init_params = {
                "processId": os.getpid(),
                "clientInfo": {"name": "AgentLayer", "version": "1.0.0"},
                "rootUri": root_uri,
                "rootPath": str(self.root_path) if self.root_path else None,
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": False,
                            "didSave": True,
                            "willSave": True,
                            "willSaveWaitUntil": False,
                        },
                        "completion": {
                            "completionItem": {
                                "snippetSupport": False,
                                "commitCharactersSupport": False,
                                "documentationFormat": ["markdown", "plaintext"],
                            },
                        },
                        "hover": {
                            "contentFormat": ["markdown", "plaintext"],
                        },
                        "definition": {"linkSupport": True},
                        "references": {},
                        "documentSymbol": {
                            "hierarchicalDocumentSymbolSupport": True,
                        },
                        "workspaceSymbol": {
                            "symbolKind": {"valueSet": list(range(1, 27))},
                        },
                        "signatureHelp": {
                            "signatureInformation": {
                                "documentationFormat": ["markdown", "plaintext"],
                            },
                        },
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "versionSupport": True,
                            "codeDescriptionSupport": True,
                            "dataSupport": True,
                        },
                        "rename": {
                            "dynamicRegistration": False,
                            "prepareSupport": True,
                        },
                    },
                    "workspace": {
                        "workspaceFolders": True,
                        "didChangeConfiguration": {
                            "dynamicRegistration": False,
                        },
                        "didChangeWatchedFiles": {
                            "dynamicRegistration": True,
                        },
                    },
                },
                "initializationOptions": self._init_options(),
                "workspaceFolders": [
                    {"uri": root_uri, "name": (self.root_path or Path(".")).name}
                ] if root_uri else None,
            }
            resp = self._send_request("initialize", init_params)
            if resp is None or "error" in resp:
                err = resp.get("error", {}) if resp else {}
                self._init_error = f"initialize failed: {err.get('message', 'no response')}"
                self.state = LSPServerState.FAILED
                logger.error("LSP %s: %s", self.language.value, self._init_error)
                return False

            self._capabilities = resp.get("result", {})
            self._send_notification("initialized", {})
            self.state = LSPServerState.INITIALIZED
            logger.info("LSP %s: initialized", self.language.value)
            return True
        except Exception as e:
            self._init_error = f"initialize error: {e}"
            self.state = LSPServerState.FAILED
            logger.error("LSP %s: %s", self.language.value, self._init_error)
            return False

    def _init_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        if self.language == Language.PYTHON:
            opts["python"] = {"analysis": {"typeCheckingMode": "basic"}}
        elif self.language == Language.GO:
            opts["usePlaceholders"] = True
        elif self.language == Language.TYPESCRIPT:
            opts["tsserver"] = {"log": "off"}
        return opts

    def stop(self) -> None:
        self.state = LSPServerState.STOPPING
        try:
            self._send_notification("shutdown", {})
            self._send_notification("exit", {})
        except Exception:
            pass
        self._cleanup()

    def _cleanup(self) -> None:
        if self._file_watcher:
            self._file_watcher.stop()
            self._file_watcher = None
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.terminate()
            except Exception:
                pass
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                    self._process.wait(timeout=3)
                except Exception:
                    pass
            self._process = None
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()
        self._documents.clear()
        self._diagnostics.clear()
        self._pending_requests.clear()
        self._responses.clear()
        self.state = LSPServerState.STOPPED

    def _read_stdout(self) -> None:
        buf = b""
        while self._process and self._process.poll() is None:
            try:
                chunk = self._process.stdout.read(1)
                if not chunk:
                    break
                buf += chunk
                if b"\r\n\r\n" in buf:
                    header_end = buf.index(b"\r\n\r\n")
                    header = buf[:header_end].decode("utf-8", errors="replace")
                    content_length = _CONTENT_LENGTH_RE.search(header)
                    if content_length:
                        length = int(content_length.group(1))
                    else:
                        buf = buf[header_end + 4:]
                        continue
                    remaining = length
                    body_parts = [buf[header_end + 4:]]
                    buf = b""
                    while remaining > 0:
                        chunk = self._process.stdout.read(min(remaining, 8192))
                        if not chunk:
                            break
                        body_parts.append(chunk)
                        remaining -= len(chunk)
                    body = b"".join(body_parts)
                    self._handle_message(body)
            except Exception as e:
                logger.error("LSP %s stdout error: %s", self.language.value, e)
                break

    def _read_stderr(self) -> None:
        while self._process and self._process.poll() is None:
            try:
                line = self._process.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    logger.debug("LSP %s stderr: %s", self.language.value, decoded)
            except Exception:
                break

    def _handle_message(self, body: bytes) -> None:
        try:
            msg = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("LSP %s: failed to parse message: %s", self.language.value, e)
            return

        msg_id = msg.get("id")
        if msg_id is not None and "result" in msg or "error" in msg:
            with self._response_lock:
                if isinstance(msg_id, int):
                    self._responses[msg_id] = msg
                    if msg_id in self._pending_requests:
                        self._pending_requests[msg_id].set()
        elif msg.get("method") == "window/logMessage":
            params = msg.get("params", {})
            level = params.get("type", 4)
            logger.debug("LSP log[%d]: %s", level, params.get("message", ""))
        elif msg.get("method") == "textDocument/publishDiagnostics":
            self._handle_diagnostics(msg.get("params", {}))
        elif msg.get("method") == "$/progress":
            pass
        elif msg.get("method") == "client/registerCapability":
            self._handle_register_capability(msg_id, msg.get("params", {}))
        elif msg.get("method") == "workspace/applyEdit":
            self._handle_apply_edit(msg_id, msg.get("params", {}))
        else:
            method = msg.get("method", "unknown")
            logger.debug("LSP %s: unhandled server method: %s", self.language.value, method)

    def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        uri = params.get("uri", "")
        diagnostics = params.get("diagnostics", [])
        version = params.get("version", -1)
        with self._diagnostics_lock:
            self._diagnostics[uri] = DiagnosticInfo(
                uri=uri, diagnostics=diagnostics, version=version
            )
        for cb in self._on_diagnostics_callbacks:
            try:
                cb(uri, diagnostics)
            except Exception:
                pass

    def _handle_register_capability(self, msg_id: Any, params: dict[str, Any]) -> None:
        registrations = params.get("registrations", [])
        for reg in registrations:
            method = reg.get("method", "")
            options = reg.get("registerOptions", {})
            if method == "workspace/didChangeWatchedFiles":
                watchers = options.get("watchers", [])
                self._start_file_watcher(watchers)
            elif method == "workspace/didCreateFiles":
                pass
            elif method == "workspace/didDeleteFiles":
                pass
            else:
                logger.debug("LSP %s: registered capability %s", self.language.value, method)
        self._send_response(msg_id, None)

    def _handle_apply_edit(self, msg_id: Any, params: dict[str, Any]) -> None:
        label = params.get("label", "")
        edit = params.get("edit", {})
        document_changes = edit.get("documentChanges", [])
        changes = edit.get("changes", {})
        applied = True
        failed_uri: str | None = None
        failed_reason: str | None = None

        if document_changes:
            for change in document_changes:
                kind = change.get("kind", "")
                if kind == "create":
                    uri = change.get("uri", "")
                    path = _uri_to_path(uri)
                    if path:
                        try:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            options = change.get("options", {})
                            if not options.get("overwrite", False) and path.exists():
                                applied = False
                                failed_uri = uri
                                failed_reason = "file already exists"
                                break
                            if options.get("ignoreIfExists", False) and path.exists():
                                continue
                            path.write_text("", encoding="utf-8")
                        except Exception as e:
                            applied = False
                            failed_uri = uri
                            failed_reason = str(e)
                            break
                elif kind == "rename":
                    old_uri = change.get("oldUri", "")
                    new_uri = change.get("newUri", "")
                    old_path = _uri_to_path(old_uri)
                    new_path = _uri_to_path(new_uri)
                    if old_path and new_path:
                        try:
                            options = change.get("options", {})
                            if not options.get("overwrite", False) and new_path.exists():
                                applied = False
                                failed_uri = new_uri
                                failed_reason = "target already exists"
                                break
                            new_path.parent.mkdir(parents=True, exist_ok=True)
                            old_path.rename(new_path)
                            old_doc = self._documents.pop(old_uri, None)
                            if old_doc:
                                self._documents[new_uri] = old_doc
                        except Exception as e:
                            applied = False
                            failed_uri = new_uri
                            failed_reason = str(e)
                            break
                elif kind == "delete":
                    uri = change.get("uri", "")
                    path = _uri_to_path(uri)
                    if path:
                        try:
                            options = change.get("options", {})
                            if options.get("recursive", False) and path.is_dir():
                                import shutil
                                shutil.rmtree(path)
                            elif path.is_file():
                                path.unlink()
                        except Exception as e:
                            applied = False
                            failed_uri = uri
                            failed_reason = str(e)
                            break
                elif kind == "edit" or "textDocument" in change:
                    uri = change.get("textDocument", {}).get("uri", "")
                    edits = change.get("edits", [])
                    if not _apply_text_edits(uri, edits, self._documents):
                        applied = False
                        failed_uri = uri
                        failed_reason = "failed to apply text edits"
                        break
        elif changes:
            for uri, text_edits in changes.items():
                if not _apply_text_edits(uri, text_edits, self._documents):
                    applied = False
                    failed_uri = uri
                    failed_reason = "failed to apply text edits"
                    break

        result = {"applied": applied}
        if not applied and failed_uri:
            result["failureReason"] = failed_reason or "unknown"
        self._send_response(msg_id, result)

    def _start_file_watcher(self, watchers: list[dict[str, Any]]) -> None:
        if self._file_watcher:
            self._file_watcher.stop()
        if self.root_path and watchers:
            self._file_watcher = WorkspaceFileWatcher(
                root_path=self.root_path,
                watchers=watchers,
                on_change=self._on_file_change,
                debounce_ms=300,
            )
            self._file_watcher.start()

    def _on_file_change(self, uri: str, change_type: int) -> None:
        if not self.is_alive:
            return
        self._send_notification("workspace/didChangeWatchedFiles", {
            "changes": [{"uri": uri, "type": change_type}]
        })
        path = _uri_to_path(uri)
        if path and path.is_file() and change_type == 1:
            try:
                text = path.read_text(encoding="utf-8")
                if uri in self._documents:
                    self.update_document(uri, text)
                else:
                    ext = path.suffix.lstrip(".")
                    lang_id = _ext_to_language_id(ext) or self.language.value
                    self.open_document(uri, text, lang_id)
            except Exception:
                pass

    def _next_id(self) -> int:
        with self._request_id_lock:
            self._request_id += 1
            return self._request_id

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or self._process.poll() is not None:
            return
        msg = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }, ensure_ascii=False)
        body = msg.encode("utf-8")
        header = f"Content-Length: {len(body)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n"
        try:
            self._process.stdin.write(header.encode("utf-8"))
            self._process.stdin.write(body)
            self._process.stdin.flush()
        except Exception as e:
            logger.error("LSP %s: failed to send notification %s: %s", self.language.value, method, e)

    def _send_request(self, method: str, params: dict[str, Any], timeout: int = 30) -> dict[str, Any] | None:
        if not self._process or self._process.poll() is not None:
            return {"error": {"message": "LSP process not running"}}
        req_id = self._next_id()
        event = threading.Event()
        with self._response_lock:
            self._pending_requests[req_id] = event
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }, ensure_ascii=False)
        body = msg.encode("utf-8")
        header = f"Content-Length: {len(body)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n"
        try:
            self._process.stdin.write(header.encode("utf-8"))
            self._process.stdin.write(body)
            self._process.stdin.flush()
        except Exception as e:
            with self._response_lock:
                self._pending_requests.pop(req_id, None)
            return {"error": {"message": f"Failed to send request: {e}"}}
        if event.wait(timeout=timeout):
            with self._response_lock:
                resp = self._responses.pop(req_id, None)
                self._pending_requests.pop(req_id, None)
            return resp
        with self._response_lock:
            self._pending_requests.pop(req_id, None)
        return {"error": {"message": f"Request {method} timed out after {timeout}s"}}

    def _send_response(self, msg_id: Any, result: Any) -> None:
        if not self._process or self._process.poll() is not None:
            return
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }, ensure_ascii=False)
        body = msg.encode("utf-8")
        header = f"Content-Length: {len(body)}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n"
        try:
            self._process.stdin.write(header.encode("utf-8"))
            self._process.stdin.write(body)
            self._process.stdin.flush()
        except Exception:
            pass

    def open_document(self, uri: str, text: str, language_id: str | None = None) -> None:
        if language_id is None:
            language_id = self.language.value
        doc = DocumentInfo(uri=uri, version=1, content=text, language_id=language_id)
        self._documents[uri] = doc
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        })

    def update_document(self, uri: str, text: str) -> None:
        doc = self._documents.get(uri)
        if doc is None:
            self.open_document(uri, text)
            return
        doc.version += 1
        old_text = doc.content
        doc.content = text
        self._send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": doc.version},
            "contentChanges": [
                {
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {
                            "line": old_text.count("\n"),
                            "character": len(old_text.rsplit("\n", 1)[-1]) if old_text else 0,
                        },
                    },
                    "text": text,
                }
            ],
        })

    def save_document(self, uri: str) -> None:
        self._send_notification("textDocument/didSave", {
            "textDocument": {"uri": uri}
        })

    def close_document(self, uri: str) -> None:
        self._documents.pop(uri, None)
        self._send_notification("textDocument/didClose", {
            "textDocument": {"uri": uri}
        })

    def get_diagnostics(self, uri: str | None = None) -> dict[str, list[dict[str, Any]]]:
        with self._diagnostics_lock:
            if uri:
                info = self._diagnostics.get(uri)
                return {uri: info.diagnostics} if info else {}
            return {k: v.diagnostics for k, v in self._diagnostics.items()}

    def wait_for_diagnostics(self, uri: str, timeout: int | None = None) -> list[dict[str, Any]]:
        timeout = timeout or self.diagnostics_timeout_s
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._diagnostics_lock:
                # Accept empty publish (clean file) — presence of the URI key means publish arrived.
                if uri in self._diagnostics:
                    return self._diagnostics[uri].diagnostics
            time.sleep(0.05)
        return []

    def go_to_definition(self, uri: str, line: int, character: int) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "goToDefinition", "result": resp.get("result")}

    def find_references(self, uri: str, line: int, character: int) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        supports_refs = (
            self._capabilities.get("capabilities", {})
            .get("referencesProvider", False)
        )
        if supports_refs is False and self._capabilities.get("referencesProvider") is False:
            pass
        resp = self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "findReferences", "result": resp.get("result")}

    def hover(self, uri: str, line: int, character: int) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "hover", "result": resp.get("result")}

    def document_symbol(self, uri: str) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "documentSymbol", "result": resp.get("result")}

    def workspace_symbol(self, query: str) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        resp = self._send_request("workspace/symbol", {
            "query": query,
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "workspaceSymbol", "result": resp.get("result")}

    def completion(self, uri: str, line: int, character: int) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"triggerKind": 1},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "completion", "result": resp.get("result")}

    def signature_help(self, uri: str, line: int, character: int) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/signatureHelp", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "signatureHelp", "result": resp.get("result")}

    def rename(self, uri: str, line: int, character: int, new_name: str) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        self._ensure_document_open(uri)
        resp = self._send_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "newName": new_name,
        })
        if resp is None:
            return {"ok": False, "error": "No response from LSP server"}
        if "error" in resp:
            return {"ok": False, "error": resp["error"].get("message", "LSP error")}
        return {"ok": True, "operation": "rename", "result": resp.get("result")}

    def diagnostics(
        self,
        uri: str | None = None,
        wait: bool = False,
        *,
        workspace_root: Path | None = None,
        requested_path: str | None = None,
        format_for_model: bool = True,
    ) -> dict[str, Any]:
        if not self.is_alive:
            if not self.start():
                return {"ok": False, "error": self._init_error or "LSP server not available"}
        if wait and uri:
            with self._diagnostics_lock:
                self._diagnostics.pop(uri, None)
            self._ensure_document_open(uri)
            self.wait_for_diagnostics(uri)
        elif uri:
            self._ensure_document_open(uri)
        diags = self.get_diagnostics(uri)
        if not format_for_model:
            return {"ok": True, "operation": "diagnostics", "result": diags}
        return format_diagnostics_payload(
            diags,
            workspace_root=workspace_root or self.root_path,
            requested_path=requested_path,
            language=self.language.value,
            server_command=list(self._command) if self._command else None,
        )

    def _ensure_document_open(self, uri: str) -> None:
        if uri not in self._documents:
            path = _uri_to_path(uri)
            if path and path.exists():
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    text = ""
            else:
                text = ""
            ext = path.suffix.lstrip(".") if path else ""
            lang_id = _ext_to_language_id(ext) or self.language.value
            self.open_document(uri, text, lang_id)

    def restart(self) -> bool:
        self.stop()
        time.sleep(0.5)
        self._documents.clear()
        self._diagnostics.clear()
        self._pending_requests.clear()
        self._responses.clear()
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()
        self._init_error = None
        return self.start()

    def status(self) -> dict[str, Any]:
        return {
            "language": self.language.value,
            "state": self.state.value,
            "command": self._command,
            "root_path": str(self.root_path) if self.root_path else None,
            "documents_open": len(self._documents),
            "diagnostics_count": sum(len(d.diagnostics) for d in self._diagnostics.values()),
            "error": self._init_error,
            "pid": self._process.pid if self._process else None,
            "capabilities": self._capabilities,
        }


def _which(cmd: str) -> bool:
    try:
        import shutil
        return shutil.which(cmd) is not None
    except Exception:
        return False


def _uri_to_path(uri: str) -> Path | None:
    if uri.startswith("file://"):
        try:
            from urllib.parse import unquote
            return Path(unquote(uri[7:]))
        except Exception:
            return None
    return Path(uri) if not uri.startswith("/") else None


def _ext_to_language_id(ext: str) -> str | None:
    mapping = {
        "py": "python", "pyi": "python",
        "go": "go",
        "rs": "rust",
        "ts": "typescript", "tsx": "typescriptreact", "js": "javascript", "jsx": "javascriptreact",
        "java": "java",
        "rb": "ruby",
        "php": "php",
        "cs": "csharp",
        "dart": "dart",
        "ex": "elixir", "exs": "elixir",
        "hs": "haskell",
        "lua": "lua",
        "tf": "terraform",
        "sql": "sql",
    }
    return mapping.get(ext.lower())


WATCH_IGNORE_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "__pycache__",
    ".venv", "venv", "env", "dist", "build", ".next", ".output",
    "target", ".idea", ".vscode", "coverage", ".tox", ".mypy_cache",
})

WATCH_DEFAULT_EXTENSIONS = frozenset({
    ".py", ".go", ".rs", ".ts", ".tsx", ".js", ".jsx",
    ".java", ".rb", ".php", ".cs", ".dart", ".ex", ".exs",
    ".hs", ".lua", ".tf", ".sql", ".html", ".css", ".json",
    ".yaml", ".yml", ".toml", ".md",
})


class WorkspaceFileWatcher:
    def __init__(
        self,
        root_path: Path,
        watchers: list[dict[str, Any]],
        on_change: Callable[[str, int], None],
        debounce_ms: int = 300,
    ):
        self._root = root_path.resolve()
        self._watchers = watchers
        self._on_change = on_change
        self._debounce_ms = debounce_ms
        self._running = False
        self._thread: threading.Thread | None = None
        self._known_files: dict[str, float] = {}
        self._lock = threading.Lock()
        self._debounce: dict[str, threading.Timer] = {}
        self._glob_patterns: list[str] = []
        self._extensions: set[str] = set()
        self._parse_watchers()

    def _parse_watchers(self) -> None:
        for w in self._watchers:
            glob_pat = w.get("globPattern", "")
            if glob_pat:
                self._glob_patterns.append(glob_pat)
                if "." in glob_pat:
                    for part in glob_pat.replace("{", "").replace("}", "").split(","):
                        if part.startswith("*."):
                            self._extensions.add(part[1:])
        if not self._extensions:
            self._extensions = WATCH_DEFAULT_EXTENSIONS

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scan_files()
        self._thread = threading.Thread(
            target=self._poll_loop, name="lsp-file-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        for timer in self._debounce.values():
            timer.cancel()
        self._debounce.clear()

    def _scan_files(self) -> None:
        with self._lock:
            for ext in self._extensions:
                for p in self._root.rglob(f"*{ext}"):
                    if self._should_ignore(p):
                        continue
                    if self._matches_pattern(p):
                        self._known_files[str(p)] = p.stat().st_mtime

    def _poll_loop(self) -> None:
        interval = max(self._debounce_ms / 1000.0, 0.1)
        while self._running:
            time.sleep(interval)
            try:
                self._check_changes()
            except Exception:
                pass

    def _check_changes(self) -> None:
        current: dict[str, float] = {}
        for ext in self._extensions:
            for p in self._root.rglob(f"*{ext}"):
                if self._should_ignore(p):
                    continue
                if self._matches_pattern(p):
                    try:
                        current[str(p)] = p.stat().st_mtime
                    except OSError:
                        pass

        with self._lock:
            for path_str, mtime in current.items():
                prev = self._known_files.get(path_str)
                if prev is None:
                    self._known_files[path_str] = mtime
                    self._fire_event(path_str, 1)
                elif mtime != prev:
                    self._known_files[path_str] = mtime
                    self._fire_event(path_str, 2)

            for path_str in list(self._known_files):
                if path_str not in current:
                    del self._known_files[path_str]
                    self._fire_event(path_str, 3)

    def _fire_event(self, path_str: str, change_type: int) -> None:
        if path_str in self._debounce:
            self._debounce[path_str].cancel()
        timer = threading.Timer(
            self._debounce_ms / 1000.0,
            self._emit_change,
            args=[path_str, change_type],
        )
        self._debounce[path_str] = timer
        timer.start()

    def _emit_change(self, path_str: str, change_type: int) -> None:
        with self._lock:
            self._debounce.pop(path_str, None)
        uri = Path(path_str).as_uri()
        self._on_change(uri, change_type)

    def _should_ignore(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self._root)
        except ValueError:
            return True
        for part in rel.parts:
            if part in WATCH_IGNORE_DIRS:
                return True
            if part.startswith(".") and part not in (".luarc.json",):
                return True
        try:
            if path.stat().st_size > 5_000_000:
                return True
        except OSError:
            return True
        return False

    def _matches_pattern(self, path: Path) -> bool:
        if not self._glob_patterns:
            return True
        rel = str(path.relative_to(self._root))
        for pat in self._glob_patterns:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
                return True
            base = pat.lstrip("**/").lstrip("*/")
            if base and fnmatch.fnmatch(path.name, base):
                return True
        return False


def _apply_text_edits(
    uri: str,
    edits: list[dict[str, Any]],
    documents: dict[str, DocumentInfo],
) -> bool:
    path = _uri_to_path(uri)
    if not path or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    doc = documents.get(uri)
    if doc:
        doc.content = content

    line_ending = "\r\n" if "\r\n" in content[:256] else "\n"
    lines = content.split(line_ending)

    sorted_edits = sorted(
        edits,
        key=lambda e: (
            e.get("range", {}).get("start", {}).get("line", 0),
            e.get("range", {}).get("start", {}).get("character", 0),
        ),
        reverse=True,
    )

    for edit in sorted_edits:
        rng = edit.get("range", {})
        start_line = rng.get("start", {}).get("line", 0)
        start_char = rng.get("start", {}).get("character", 0)
        end_line = rng.get("end", {}).get("line", 0)
        end_char = rng.get("end", {}).get("character", 0)
        new_text = edit.get("newText", "")

        if start_line == end_line:
            line = lines[start_line]
            lines[start_line] = line[:start_char] + new_text + line[end_char:]
        else:
            first_line = lines[start_line][:start_char] + new_text
            last_part = lines[end_line][end_char:]
            removed = end_line - start_line
            del lines[start_line + 1 : end_line + 1]
            lines[start_line] = first_line + last_part

    new_content = line_ending.join(lines)
    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception:
        return False
    if doc:
        doc.content = new_content
        doc.version += 1
    return True


class LSPServerManager:
    def __init__(self):
        self._servers: dict[str, LSPClient] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        language: Language,
        root_path: Path | None = None,
        server_cmd: list[str] | None = None,
    ) -> LSPClient:
        key = f"{language.value}:{root_path}" if root_path else language.value
        with self._lock:
            if key in self._servers:
                client = self._servers[key]
                if client.is_alive:
                    return client
                client.stop()
                del self._servers[key]
            client = LSPClient(
                language=language,
                root_path=root_path,
                server_cmd=server_cmd,
            )
            self._servers[key] = client
            return client

    def get_by_extension(self, ext: str, root_path: Path | None = None) -> LSPClient | None:
        language = _ext_to_language(ext)
        if language is None:
            return None
        return self.get_or_create(language, root_path)

    def list_servers(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.status() for s in self._servers.values()]

    def shutdown_all(self) -> None:
        with self._lock:
            for server in self._servers.values():
                server.stop()
            self._servers.clear()


def _ext_to_language(ext: str) -> Language | None:
    ext_lower = ext.lower()
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if ext_lower in exts:
            return lang
    return None


_manager = LSPServerManager()


def get_manager() -> LSPServerManager:
    return _manager
