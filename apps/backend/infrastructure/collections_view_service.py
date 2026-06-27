"""Infrastructure adapter for dashboard view helpers used by collections."""

from __future__ import annotations

from typing import Any

from apps.backend.dashboard.data_compute import finalize_dashboard_data
from apps.backend.dashboard.data_paths import get_path, set_path, top_level_key
from apps.backend.dashboard.layout_tree import data_paths_from_blocks, iter_layout_blocks
from apps.backend.domain.collections import bindings, projection, service
from apps.backend.infrastructure.db import db


class _CollectionsViewDeps:
    get_path = staticmethod(get_path)
    set_path = staticmethod(set_path)
    top_level_key = staticmethod(top_level_key)
    iter_layout_blocks = staticmethod(iter_layout_blocks)
    data_paths_from_blocks = staticmethod(data_paths_from_blocks)
    finalize_dashboard_data = staticmethod(finalize_dashboard_data)

    @staticmethod
    def delete_collection_items_for_list(collection_id, list_key: str) -> None:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM collection_items WHERE collection_id = %s AND list_key = %s",
                    (collection_id, list_key),
                )
            conn.commit()


bindings.register_collections_view_dependencies(_CollectionsViewDeps())
projection.register_collections_projection_dependencies(_CollectionsViewDeps())
service.register_collections_service_dependencies(_CollectionsViewDeps())

project_dashboard_data = projection.project_dashboard_data
resolve_bindings_for_dashboard = service.resolve_bindings_for_dashboard
append_items = service.append_items
update_item = service.update_item
delete_item = service.delete_item
patch_fields = service.patch_fields
