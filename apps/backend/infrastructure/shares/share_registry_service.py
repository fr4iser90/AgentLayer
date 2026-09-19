"""Import-time wiring for the share adapter registry (ADR 0014 step 2).

Importing this module registers the adapters this deployment ships with.
Like the sibling ``*_service`` modules, the registration is a side effect
of import so the domain layer never has to know which infrastructure
implementations are loaded.

A type that is not registered here is not readable through the generic
share path. That fails closed: an unregistered type can still be granted
(the write side is open on purpose), it just cannot be read — which is the
opposite of the pre-registry behaviour where a grant looked like access.
"""

from __future__ import annotations

from apps.backend.domain.shares.adapters import register_default_share_adapters

register_default_share_adapters()
