"""Identity commands."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChangeUserRoleCommand:
    user_id: uuid.UUID
    role: str
