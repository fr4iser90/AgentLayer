from __future__ import annotations

from apps.backend.infrastructure.agent_runtime.llm_queue_policy import invalidate_user_priority_cache
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.instance_setup_service import (
    apply_setup_llm_endpoint,
    build_setup_status,
    create_first_admin,
    enforce_setup_rate_limit,
    probe_llm_endpoint,
    setup_admin_claim_if_needed,
    validate_setup_email,
    validate_setup_password,
    validate_setup_token,
)
from apps.backend.infrastructure.identity.otp_register_guard import (
    enforce_otp_register_rate_limit,
    require_https_or_loopback_for_otp_register,
)
from apps.backend.infrastructure.identity.setup_catalog_service import (
    SetupPreferencesBody,
    apply_enable_chat_provider_embedding,
    apply_setup_preferences,
    apply_setup_skip_suggestions,
    build_setup_catalog,
    test_embedding_model,
)
from apps.backend.infrastructure.platform.config import PLUGINS_DIR, config
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.providers.model_catalog_providers import (
    fetch_full_model_catalog,
    merge_model_catalog_rows,
)
