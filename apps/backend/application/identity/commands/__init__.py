"""Identity commands.

Empty on purpose. The one command this package held wrote the compatibility column
``users.role``; ADR 0011 forbids any code path from elevating with it, so nothing may
replace it here. Elevation lives in ``users.site_role`` and is read through
``apps.backend.domain.identity.roles``.
"""
