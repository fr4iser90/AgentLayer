"""Infrastructure adapter for collection DB ports."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.collections import attachments_db, db as collections_db
from apps.backend.infrastructure.db import db


class _CollectionsDbDeps:
    @staticmethod
    def pool() -> Any:
        return db.pool()


_deps = _CollectionsDbDeps()
collections_db.register_collections_db_dependencies(_deps)
attachments_db.register_collection_attachments_db_dependencies(_deps)

attachment_delete_with_access = attachments_db.attachment_delete_with_access
attachment_get_with_access = attachments_db.attachment_get_with_access
attachment_insert = collections_db.attachment_insert
collection_ensure = collections_db.collection_ensure
collection_get = collections_db.collection_get
collection_get_by_id = collections_db.collection_get_by_id
collection_list = collections_db.collection_list
collection_metadata_patch = collections_db.collection_metadata_patch
file_ids_in_value = attachments_db.file_ids_in_value
item_delete = collections_db.item_delete
item_update = collections_db.item_update
items_append = collections_db.items_append
items_list = collections_db.items_list
normalize_slug = collections_db.normalize_slug
parse_file_ref = attachments_db.parse_file_ref
