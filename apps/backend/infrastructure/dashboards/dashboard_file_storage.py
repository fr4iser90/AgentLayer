"""Filesystem IO for ``user_attachments.storage_relpath`` under the configured upload root."""

from __future__ import annotations

from pathlib import Path


def _safe_child(root: Path, relpath: str) -> Path:
    if ".." in Path(relpath).parts:
        raise ValueError("invalid path")
    root_r = root.resolve()
    full = (root_r / relpath).resolve()
    full.relative_to(root_r)
    return full


def write_bytes(root: Path, relpath: str, data: bytes) -> None:
    dest = _safe_child(root, relpath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def read_bytes(root: Path, relpath: str) -> bytes:
    return _safe_child(root, relpath).read_bytes()


def unlink_if_exists(root: Path, relpath: str) -> None:
    try:
        p = _safe_child(root, relpath)
        if p.is_file():
            p.unlink()
    except (OSError, ValueError):
        pass
