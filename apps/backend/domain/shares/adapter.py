"""The share adapter protocol (ADR 0014 step 1).

Derived from the two adapters that already exist — ``dashboard_grant`` and
``collection_grant`` — rather than invented. Both have the same four parts:
a resource type, a way to normalise and match the identifier, a grant
lookup, and a projection of what the grantee is allowed to see. Naming
those parts is what lets a registry hold them.

**Principle 1 lives here, at the protocol boundary.** A projection is what
the grantee receives, so the projection must never carry a URL, a secret, a
token or a handle. Enforcing that in the registry rather than in each adapter
is what makes the ``§1.6``/``§1.7`` class of bug impossible on this path
instead of merely absent: an adapter that leaks cannot serve.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

# Key names that mean a credential escaped into a grantee-visible projection.
#
# Matching is on the *key*, never on a value substring. ``source_hint``
# legitimately takes the literal string "ics_url" as its value for
# non-Google calendar feeds, so a substring check produces false positives
# and, worse, teaches people to weaken the guard until it passes.
CREDENTIAL_KEY_NAMES = frozenset(
    {
        "ics_url",
        "url",
        "uri",
        "secret",
        "ciphertext",
        "token",
        "access_token",
        "refresh_token",
        "bearer",
        "api_key",
        "apikey",
        "password",
        "passwd",
        "credential",
        "credentials",
        "private_key",
        "auth_header",
    }
)


def find_credential_keys(projection: Any, _path: str = "") -> list[str]:
    """Return every credential-shaped key found anywhere in ``projection``.

    Empty list means the projection is clear. Dicts, sequences and named
    tuples are all walked; a named tuple is inspected by field name via
    ``_asdict`` so a field called ``secret`` is caught rather than indexed
    past.
    """
    found: list[str] = []

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            items: list[tuple[Any, Any]] = list(obj.items())
        elif hasattr(obj, "_asdict") and callable(getattr(obj, "_asdict")):
            try:
                items = list(obj._asdict().items())
            except Exception:  # pragma: no cover - defensive
                return
        elif isinstance(obj, (list, tuple, set, frozenset)):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]" if path else f"[{i}]")
            return
        else:
            return

        for key, value in items:
            child = f"{path}.{key}" if path else str(key)
            if str(key).strip().lower() in CREDENTIAL_KEY_NAMES:
                found.append(child)
            walk(value, child)

    walk(projection, _path)
    return found


@runtime_checkable
class ShareAdapter(Protocol):
    """One shareable resource.

    Implementations must be side-effect free with respect to the grant: they
    read the grant and project what it allows. They must not return anything
    the grantee could use outside this path — see ``find_credential_keys``.
    """

    #: Every resource_type string this adapter answers for, including legacy
    #: aliases. Registration binds each string to this adapter.
    resource_types: tuple[str, ...]

    #: The policy keys this adapter actually honours. Declared here so step 3
    #: can reject unknown keys at write time instead of storing a restriction
    #: that nothing reads (ADR 0014 §1.9).
    policy_fields: frozenset[str]

    def normalize_identifier(self, raw: str) -> str | None:
        """Canonical form of a resource identifier, or None if malformed.

        Returning None means "this cannot name a resource", which the caller
        must treat as a refusal rather than an empty lookup.
        """
        ...

    def resolve(
        self,
        *,
        owner_user_id: uuid.UUID,
        grantee_user_id: uuid.UUID,
        identifier: str,
        request: dict[str, Any] | None = None,
    ) -> Any | None:
        """The projection this grant allows, or None when nothing is granted.

        ``None`` means "no active grant". It must not be conflated with an
        empty projection, which means "granted, and there is nothing to
        show" — the two read very differently to a grantee.

        ``request`` carries per-call parameters the generic tool received
        (for example a requested horizon). Adapters must treat it as
        untrusted input and clamp it against their own policy — the grant,
        not the caller, decides how much is visible.
        """
        ...

    def list_shared(self, grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Resources of this type visible to ``grantee_user_id``.

        Adapters with no listing affordance return ``[]``.
        """
        ...
