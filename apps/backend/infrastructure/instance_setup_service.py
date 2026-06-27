"""Infrastructure adapter for first-instance setup use cases."""

from __future__ import annotations

from typing import Any

from apps.backend.dashboard.db import ensure_default_dashboard_for_new_user
from apps.backend.domain import instance_setup as domain
from apps.backend.domain.admin_setup import is_first_start, try_create_initial_admin_from_env
from apps.backend.domain.catalog_chat_llm import cached_llm_reachable
from apps.backend.infrastructure.auth import insert_user_with_cursor
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.model_catalog_providers import list_provider_specs
from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache
from apps.backend.infrastructure.operator_settings import (
    external_api_headers,
    external_models_list_url,
    invalidate_operator_settings_cache,
)


class _InstanceSetupDeps:
    is_first_start = staticmethod(is_first_start)
    try_create_initial_admin_from_env = staticmethod(try_create_initial_admin_from_env)
    cached_llm_reachable = staticmethod(cached_llm_reachable)
    list_provider_specs = staticmethod(list_provider_specs)
    pool = staticmethod(db.pool)
    insert_user_with_cursor = staticmethod(insert_user_with_cursor)
    ensure_default_dashboard_for_new_user = staticmethod(ensure_default_dashboard_for_new_user)
    operator_provider_endpoints_list_all = staticmethod(db.operator_provider_endpoints_list_all)
    external_llm_endpoints_list_all = staticmethod(db.external_llm_endpoints_list_all)
    operator_provider_endpoints_sync = staticmethod(db.operator_provider_endpoints_sync)
    external_api_headers = staticmethod(external_api_headers)
    external_models_list_url = staticmethod(external_models_list_url)
    invalidate_operator_settings_cache = staticmethod(invalidate_operator_settings_cache)
    invalidate_model_catalog_cache = staticmethod(invalidate_model_catalog_cache)


domain.register_instance_setup_dependencies(_InstanceSetupDeps())

apply_setup_llm_endpoint = domain.apply_setup_llm_endpoint
build_setup_status = domain.build_setup_status
create_first_admin = domain.create_first_admin
emit_initial_setup_notice_at_end = domain.emit_initial_setup_notice_at_end
enforce_setup_rate_limit = domain.enforce_setup_rate_limit
probe_llm_endpoint = domain.probe_llm_endpoint
setup_admin_claim_if_needed = domain.setup_admin_claim_if_needed
validate_setup_email = domain.validate_setup_email
validate_setup_password = domain.validate_setup_password
validate_setup_token = domain.validate_setup_token
