"""Agent runtime read queries."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetAgentRunQuery:
    run_id: uuid.UUID
