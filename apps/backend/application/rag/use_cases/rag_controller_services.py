from __future__ import annotations

import apps.backend.infrastructure.rag.rag_core as rag_service
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.memory import memory_service
from apps.backend.infrastructure.platform.public_error import http_500_detail
from apps.backend.infrastructure.rag.rag_docs_file_ingest_service import ingest_markdown_tree, resolve_docs_root
from apps.backend.infrastructure.settings import operator_settings
