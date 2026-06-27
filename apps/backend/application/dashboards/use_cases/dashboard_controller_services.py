from __future__ import annotations

from apps.backend.infrastructure.collections import collections_db_service as attachments_db
from apps.backend.infrastructure.collections import collections_db_service as col_db
from apps.backend.infrastructure.collections import collections_view_service
from apps.backend.infrastructure.dashboards import dashboard_db
from apps.backend.infrastructure.dashboards import dashboard_file_storage as file_storage
from apps.backend.infrastructure.dashboards import dashboard_public_share as public_share
from apps.backend.infrastructure.dashboards.dashboard_block_ref import render_block_from_dashboard
from apps.backend.infrastructure.dashboards.dashboard_bootstrap import (
    dashboard_tables_exist,
    ensure_dashboard_schema,
)
from apps.backend.infrastructure.dashboards.dashboard_bundle import (
    kind_catalog,
    kinds_with_schema_sql,
    kinds_with_templates,
    template_catalog,
    template_ids_with_templates,
)
from apps.backend.infrastructure.dashboards.dashboard_create_helpers import resolve_create_target
from apps.backend.infrastructure.dashboards.dashboard_layout_proposals import (
    apply_layout_proposal,
    get_latest_proposal_set,
    get_proposal_set,
)
from apps.backend.infrastructure.dashboards.dashboard_list_ops import append_list_rows
from apps.backend.infrastructure.dashboards.dashboard_pins import pin_block_to_dashboard
from apps.backend.infrastructure.dashboards.dashboard_setup import attach_onboarding, onboarding_for_kind
from apps.backend.infrastructure.dashboards.dashboard_template_ops import (
    export_template_payload,
    validate_template_import,
)
from apps.backend.infrastructure.dashboards.dashboard_upload_bytes import (
    normalized_content_type,
    sniff_image_mime,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.settings.operator_settings import (
    effective_dashboard_upload_max_bytes,
    effective_dashboard_upload_mime,
)
