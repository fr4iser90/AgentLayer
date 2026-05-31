"""Per-user writable output under ``$AGENT_DATA_DIR/output/<user-id>/``."""

from __future__ import annotations

import os
from pathlib import Path


def agent_data_dir() -> Path:
    raw = os.environ.get("AGENT_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("/data")


def user_output_root(user_id: int | str | None) -> Path:
    uid = str(user_id or "anonymous").strip() or "anonymous"
    return agent_data_dir() / "output" / uid


def user_output_subdir(user_id: int | str | None, *parts: str) -> Path:
    root = user_output_root(user_id)
    for p in parts:
        seg = str(p).strip().strip("/")
        if seg:
            root = root / seg
    root.mkdir(parents=True, exist_ok=True)
    return root
