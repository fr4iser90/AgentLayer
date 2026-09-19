"""Friends integration helpers — colocated with friends tools."""

from plugins.tools.integrations.friends.lib.common import (
    resolve_contact_email,
    resolve_friend_by_name,
    resolve_message_recipient,
    resource_type_label,
)

__all__ = [
    "resolve_contact_email",
    "resolve_friend_by_name",
    "resolve_message_recipient",
    "resource_type_label",
]
