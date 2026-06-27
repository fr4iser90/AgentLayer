"""Per-user writable output under ``$AGENT_DATA_DIR/output/<user-id>/``."""

from __future__ import annotations

from pathlib import Path


def user_output_root(user_id: int | str | None, *, base_dir: Path = Path("/data")) -> Path:
    uid = str(user_id or "anonymous").strip() or "anonymous"
    return base_dir / "output" / uid


def user_output_subdir(
    user_id: int | str | None,
    *parts: str,
    base_dir: Path = Path("/data"),
) -> Path:
    root = user_output_root(user_id, base_dir=base_dir)
    for p in parts:
        seg = str(p).strip().strip("/")
        if seg:
            root = root / seg
    root.mkdir(parents=True, exist_ok=True)
    return root
