"""Registry adapters for the resource types that already work.

Both wrappers delegate to the existing domain adapters and change no
behaviour (ADR 0014 step 2). Their job is to expose what those modules
already do through the registry contract, so the contract is derived from
code that is known to work rather than from a design sketch.
"""

from apps.backend.domain.shares.adapters.collection_adapter import (
    CollectionShareAdapter,
)
from apps.backend.domain.shares.adapters.dashboard_adapter import (
    DashboardShareAdapter,
)

__all__ = [
    "CollectionShareAdapter",
    "DashboardShareAdapter",
    "register_default_share_adapters",
]


def register_default_share_adapters() -> None:
    """Register the adapters this deployment ships with.

    Called from the infrastructure wiring alongside the
    ``register_*_dependencies`` calls. A type that is not registered here is
    not readable through the generic path — which fails closed, the right
    direction (ADR 0014 §6.3).
    """
    from apps.backend.domain.shares.registry import register_share_adapter

    register_share_adapter(DashboardShareAdapter())
    register_share_adapter(CollectionShareAdapter())
