"""Registry adapters for the resource types that already work.

Both wrappers delegate to the existing domain adapters and change no
behaviour (ADR 0014 step 2). Their job is to expose what those modules
already do through the registry contract, so the contract is derived from
code that is known to work rather than from a design sketch.
"""

from apps.backend.domain.shares.adapters.calendar_adapter import (
    CalendarShareAdapter,
)
from apps.backend.domain.shares.adapters.collection_adapter import (
    CollectionShareAdapter,
)
from apps.backend.domain.shares.adapters.dashboard_adapter import (
    DashboardShareAdapter,
)

# Singletons on purpose. The registry refuses to rebind a type to a
# *different* adapter, so handing out a fresh instance per call would make a
# second registration attempt — an app reload, a second import path — fail
# at startup with "already registered to DashboardShareAdapter, refusing
# DashboardShareAdapter".
_DEFAULT_DASHBOARD = DashboardShareAdapter()
_DEFAULT_COLLECTION = CollectionShareAdapter()
_DEFAULT_CALENDAR = CalendarShareAdapter()

__all__ = [
    "CalendarShareAdapter",
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

    Idempotent: repeated calls rebind the same instances and are a no-op.
    """
    from apps.backend.domain.shares.registry import register_share_adapter

    register_share_adapter(_DEFAULT_DASHBOARD)
    register_share_adapter(_DEFAULT_COLLECTION)
    register_share_adapter(_DEFAULT_CALENDAR)
