from __future__ import annotations

from apps.backend.infrastructure.dashboards import dashboard_db
from apps.backend.infrastructure.dashboards import dashboard_file_storage as file_storage
from apps.backend.infrastructure.dashboards.dashboard_upload_bytes import normalized_content_type
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.media import media_db, media_policy
from apps.backend.infrastructure.media.stream_probe import validate_stream_for_library
from apps.backend.infrastructure.media.upload_bytes import sniff_media_mime
from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.platform.public_error import http_500_detail
