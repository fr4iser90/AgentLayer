"""Share adapter registry (ADR 0014 steps 1–2).

The registry is what makes *generic* sharing safe. Without it, a generic
"read any resource" tool is an exfiltration machine: hand it a type string
and an identifier and it reads whatever is behind them. Bounding the
readable set to the types someone wrote a grant-enforcing adapter for is
the whole point (§5.2).

Two things this layer guarantees that individual adapters cannot guarantee
for each other:

* **Unknown type is not readable.** ``resolve_projection`` returns a
  refusal for any type with no adapter, so an unregistered type cannot be
  read even though it can still be *granted* (the write side stays open on
  purpose, §1.4).
* **A leaking adapter cannot serve.** Every projection passes the
  Principle 1 check before it is handed back. An adapter that returns a
  credential raises instead of returning — fail closed at the boundary,
  rather than relying on each adapter author to remember.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.backend.domain.shares.adapter import ShareAdapter, find_credential_keys
from apps.backend.domain.shares.catalog import canonical_resource_type


class ShareRegistryError(RuntimeError):
    """A registration or a projection violated the adapter contract."""


@dataclass(frozen=True)
class ResolveOutcome:
    """Result of a registry resolve.

    ``refusal`` is None only when a projection was produced. Keeping the
    refusal reason separate stops a caller from having to guess whether
    ``None`` meant "no grant", "no adapter" or "bad identifier" — those
    need different messages and only one of them is the grantee's fault.
    """

    adapter: ShareAdapter | None
    projection: Any | None
    refusal: str | None

    @property
    def served(self) -> bool:
        return self.refusal is None


_adapters: dict[str, ShareAdapter] = {}


def register_share_adapter(adapter: ShareAdapter) -> None:
    """Bind every resource_type an adapter answers for to that adapter.

    Re-registering the same adapter instance is idempotent, so repeated
    import-time wiring is harmless. Binding a type that a *different*
    adapter already owns raises — a silent override would move which
    adapter enforces a live grant without anyone deciding it.
    """
    types = tuple(getattr(adapter, "resource_types", ()) or ())
    if not types:
        raise ShareRegistryError(
            f"{type(adapter).__name__} declares no resource_types"
        )
    for rtype in types:
        key = canonical_resource_type(rtype)
        if not key:
            raise ShareRegistryError(
                f"{type(adapter).__name__} declares invalid resource_type {rtype!r}"
            )
        existing = _adapters.get(key)
        if existing is not None and existing is not adapter:
            raise ShareRegistryError(
                f"resource_type {key!r} already registered to "
                f"{type(existing).__name__}, refusing {type(adapter).__name__}"
            )
        _adapters[key] = adapter


def get_share_adapter(resource_type: str) -> ShareAdapter | None:
    key = canonical_resource_type(resource_type)
    return _adapters.get(key) if key else None


def registered_resource_types() -> tuple[str, ...]:
    return tuple(sorted(_adapters))


def reset_share_registry() -> None:
    """Drop all bindings. Test-only; production wiring is import-time."""
    _adapters.clear()


def resolve_projection(
    *,
    resource_type: str,
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    identifier: str,
) -> ResolveOutcome:
    """Resolve a grant through its adapter and gate the projection.

    Never returns a projection that carries a credential-shaped key.
    """
    adapter = get_share_adapter(resource_type)
    if adapter is None:
        return ResolveOutcome(None, None, "no_adapter_registered")

    norm = adapter.normalize_identifier(identifier)
    if not norm:
        return ResolveOutcome(adapter, None, "malformed_identifier")

    projection = adapter.resolve(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        identifier=norm,
    )
    if projection is None:
        return ResolveOutcome(adapter, None, "not_granted")

    leaked = find_credential_keys(projection)
    if leaked:
        # Fail closed. Do not return the projection and do not downgrade to a
        # warning: this path feeds a grantee's agent context, and the point of
        # Principle 1 is that the credential never becomes a value they hold.
        raise ShareRegistryError(
            f"{type(adapter).__name__} projection for {resource_type!r} carries "
            f"credential-shaped key(s): {', '.join(sorted(set(leaked)))}"
        )

    return ResolveOutcome(adapter, projection, None)


def describe_registered() -> list[dict[str, Any]]:
    """What the share UI can render without knowing any type by hand (step 5)."""
    out: list[dict[str, Any]] = []
    for key in registered_resource_types():
        adapter = _adapters[key]
        out.append(
            {
                "resource_type": key,
                "adapter": type(adapter).__name__,
                "policy_fields": sorted(getattr(adapter, "policy_fields", ()) or ()),
                "listable": bool(getattr(adapter, "supports_list", False)),
            }
        )
    return out
