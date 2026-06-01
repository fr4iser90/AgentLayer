"""SQL safety utilities for the AgentLayer backend.

Provides column-name whitelisting for dynamic SQL UPDATE statements
and secure temporary file creation helpers.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

__all__ = ["build_safe_set_clause", "safe_mkstemp", "SafeSetClause"]


class SafeSetClause:
    """Represents a validated, parameterized SET clause for SQL UPDATE statements.

    Attributes:
        set_expr: The validated SET clause string (e.g. "col1 = %s, col2 = %s").
        params: The tuple of values to bind to the %s placeholders.
    """

    __slots__ = ("set_expr", "params")

    def __init__(self, set_expr: str, params: tuple[Any, ...]) -> None:
        self.set_expr = set_expr
        self.params = params

    @property
    def is_empty(self) -> bool:
        return not self.set_expr


def build_safe_set_clause(
    allowed_columns: set[str],
    updates: dict[str, Any],
    *,
    extra_columns: dict[str, str] | None = None,
) -> SafeSetClause:
    """Build a safe, parameterized SET clause from a dict of updates.

    Validates that every column name in *updates* is present in the
    *allowed_columns* whitelist before interpolating it into SQL.

    Args:
        allowed_columns: Set of allowed column names for the target table.
        updates: Mapping of column_name -> new_value. Only columns present
                 in *allowed_columns* are included in the result.
        extra_columns: Optional dict mapping update keys to literal column
                       expressions (e.g. {"updated_at": "updated_at = now()"}).
                       These bypass whitelisting since they use fixed literals.

    Returns:
        A ``SafeSetClause`` with the validated SET expression and bound
        parameter tuple.

    Raises:
        ValueError: If a column name in *updates* is not in the whitelist.
    """
    parts: list[str] = []
    params: list[Any] = []

    for col, val in updates.items():
        if col not in allowed_columns:
            raise ValueError(f"Invalid column: {col}")
        parts.append(f"{col} = %s")
        params.append(val)

    # Handle extra literal columns (e.g. "updated_at = now()")
    if extra_columns:
        for key, literal_expr in extra_columns.items():
            if key in updates:
                val = updates[key]
                parts.append(literal_expr.replace("%s", "%s") if "%s" in literal_expr else f"{literal_expr} = %s")
                params.append(val)

    if not parts:
        return SafeSetClause("", tuple())

    return SafeSetClause(", ".join(parts), tuple(params))


def safe_mkstemp(
    suffix: str = "",
    prefix: str = "tmp",
    dir: str | None = None,
    *,
    text: bool = False,
    mode: int = 0o600,
) -> tuple[int, str]:
    """Create a secure temporary file with restrictive permissions.

    Wrapper around ``tempfile.mkstemp`` that enforces ``mode=0o600``
    (owner read/write only) unless explicitly overridden.

    Args:
        suffix: Suffix for the tempfile name.
        prefix: Prefix for the tempfile name.
        dir: Directory in which to create the tempfile.
        text: If True, open in text mode (default False = binary).
        mode: File mode/permissions (default 0o600 = owner rw-only).

    Returns:
        A ``(fd, path)`` tuple from ``tempfile.mkstemp``.

    Note:
        The caller is responsible for closing the file descriptor and
        deleting the file when done.
    """
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir, text=text)
    os.chmod(path, mode)
    return fd, path
