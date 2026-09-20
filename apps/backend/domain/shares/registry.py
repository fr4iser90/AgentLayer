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
from apps.backend.domain.shares import projections as _projections


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


def policy_fields_for(resource_type: str) -> frozenset[str] | None:
    """The policy keys this resource type may carry, or None if nobody knows.

    A registered adapter declares what its reader actually acts on, so its
    set is authoritative and narrower than the global validator's. ``None``
    means there is no adapter and therefore nobody who can say a field is
    meaningless — the caller must fall back to the global set, because the
    write side stays open on purpose (ADR 0014 §1.4).

    The distinction matters: ``frozenset()`` (adapter exists, honours
    nothing) and ``None`` (no adapter) are different answers and must not be
    collapsed.
    """
    adapter = get_share_adapter(resource_type)
    if adapter is None:
        return None
    return frozenset(getattr(adapter, "policy_fields", ()) or ())


def reset_share_registry() -> None:
    """Drop all bindings. Test-only; production wiring is import-time."""
    _adapters.clear()


def resolve_projection(
    *,
    resource_type: str,
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    identifier: str,
    request: dict[str, Any] | None = None,
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
        request=request,
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


@dataclass(frozen=True)
class PublishOutcome:
    """Result of an owner publishing a projection of their own resource."""

    projection: Any | None
    refusal: str | None

    @property
    def served(self) -> bool:
        return self.refusal is None


def publish_projection(
    *,
    resource_type: str,
    owner_user_id: uuid.UUID,
    identifier: str,
    kind: str | None = None,
) -> PublishOutcome:
    """Publish the owner's narrowed view of their own resource (step 6).

    Reached through the registry rather than called on the adapter directly,
    so Principle 2 has one meaning here too: nothing gets between the caller
    and the stored row except this function and the store's own credential
    gate. A caller that could hand a payload straight to the store would be
    a caller that could store a credential.

    This is an owner-side operation. It reads the owner's own source with
    the owner's own credential and writes a narrowed projection; it does
    not grant anything, and granting is still what makes it readable.
    """
    adapter = get_share_adapter(resource_type)
    if adapter is None:
        return PublishOutcome(None, "no_adapter_registered")
    if not _projections.projection_backed(adapter):
        return PublishOutcome(None, "not_projection_backed")

    norm = adapter.normalize_identifier(identifier)
    if not norm:
        return PublishOutcome(None, "malformed_identifier")

    kinds = _projections.projection_kinds_for(adapter)
    chosen = kind or _projections.default_projection_kind(adapter)
    if kinds and chosen not in kinds:
        return PublishOutcome(None, "unknown_projection_kind")

    try:
        payload = adapter.publish_projection(
            owner_user_id=owner_user_id, identifier=norm, kind=chosen
        )
    except _projections.ShareProjectionPublishError as exc:
        return PublishOutcome(None, str(exc) or "publish_failed")

    if payload is None:
        return PublishOutcome(None, "publish_returned_nothing")

    stored = _projections.store_projection(
        adapter,
        owner_user_id=owner_user_id,
        resource_type=resource_type,
        resource_identifier=norm,
        kind=chosen,
        payload=payload,
    )
    return PublishOutcome(stored, None)


def describe_registered() -> list[dict[str, Any]]:
    """One entry per registry key, including legacy aliases.

    Introspection-level: useful for seeing exactly what is bound, including
    the fact that an alias has its own key. Not what a picker should render —
    see ``describe_shareable_types`` for that.
    """
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


def describe_shareable_types() -> list[dict[str, Any]]:
    """One entry per adapter, keyed on its canonical type (ADR 0014 step 5).

    ``describe_registered()`` lists a legacy alias next to the id it aliases,
    so a UI rendering it would offer "calendar" and "google calendar" as two
    separate things to share. Here the adapter's **first declared type is
    canonical** and the rest are reported as aliases of it, so the shareable
    set is the set of things that are actually distinct.

    This is the *readable* set, not the grantable one. Any well-formed type
    id can still be stored as a grant (§1.4); an entry here means an adapter
    enforces the grant before anything is served. A type absent from this list
    can be granted but does nothing yet — which is the difference this ADR
    exists to make visible.
    """
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in registered_resource_types():
        adapter = _adapters[key]
        if id(adapter) in seen:
            continue
        seen.add(id(adapter))
        declared = tuple(getattr(adapter, "resource_types", ()) or ())
        canonical = declared[0] if declared else key
        # The identifier this type takes when none is given. Asking the adapter
        # rather than assuming "primary": a calendar share is one-per-user and
        # defaults cleanly, but a collection needs a slug and a dashboard a
        # UUID, so for those the honest answer is "none — supply one".
        try:
            default_identifier = adapter.normalize_identifier("") or None
        except Exception:
            default_identifier = None
        out.append(
            {
                "resource_type": canonical,
                "policy_fields": sorted(getattr(adapter, "policy_fields", ()) or ()),
                "listable": bool(getattr(adapter, "supports_list", False)),
                "aliases": list(declared[1:]),
                "default_identifier": default_identifier,
                # Empty for a type that reads live. Non-empty means the owner
                # can choose a shape, and the UI can offer that choice
                # instead of guessing whether one exists.
                "projection_kinds": list(_projections.projection_kinds_for(adapter)),
                "default_projection_kind": _projections.default_projection_kind(adapter),
            }
        )
    # Sorted, not registry-insertion order: this feeds a picker and an agent
    # help string, both of which should read the same way every time.
    out.sort(key=lambda e: e["resource_type"])
    return out
