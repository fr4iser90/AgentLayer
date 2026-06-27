from __future__ import annotations

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.tools.tool_operator_policy_db import (
    list_policies,
    policies_map,
    replace_all_policies,
)
