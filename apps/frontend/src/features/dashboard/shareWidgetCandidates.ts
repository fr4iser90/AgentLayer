/**
 * The (owner, resource type) pairs a share widget may point at.
 *
 * A candidate is offered only when the preview it implies actually exists:
 * the friend granted us the type **and** the type is projection-backed.
 * Offering a grant with no preview would draw an empty box and read as a
 * broken share rather than an absent one — the widget cannot tell those
 * apart once it is pointed somewhere, but the picker can before it points.
 *
 * The catalog is matched by canonical id **and** alias. A grant written
 * before the registry rename still says `calendar`; matching by id alone
 * would hide a share that works. Matching by alias alone would hand the
 * widget the legacy id, which then asks for a type the catalog does not
 * list. Both directions of that mistake have already happened here, so the
 * candidate always reports `entry.id` — the canonical id — regardless of
 * which spelling the grant used.
 */

export type ShareCandidate = {
  /** Stable option value: canonical owner + type, never a display string. */
  key: string;
  ownerUserId: string;
  displayName: string;
  resourceType: string;
  resourceName: string;
};

type CatalogEntry = {
  id?: unknown;
  name?: unknown;
  aliases?: unknown;
  previewable?: unknown;
};

type IncomingGrant = {
  owner_user_id?: unknown;
  resource_type?: unknown;
  display_name?: unknown;
  email?: unknown;
};

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Index of every spelling a catalog entry answers to, keyed to that entry. */
function indexCatalog(catalog: CatalogEntry[]): Map<string, CatalogEntry> {
  const bySpelling = new Map<string, CatalogEntry>();
  for (const entry of catalog) {
    const id = str(entry?.id);
    if (!id) continue;
    bySpelling.set(id, entry);
    const aliases = Array.isArray(entry?.aliases) ? entry.aliases : [];
    for (const alias of aliases) {
      const spelling = str(alias);
      if (spelling) bySpelling.set(spelling, entry);
    }
  }
  return bySpelling;
}

export function buildShareCandidates(
  grants: IncomingGrant[],
  catalog: CatalogEntry[],
): ShareCandidate[] {
  const bySpelling = indexCatalog(catalog);

  const byKey = new Map<string, ShareCandidate>();
  for (const grant of grants ?? []) {
    const entry = bySpelling.get(str(grant?.resource_type));
    // `previewable` is the backend's statement about what the read returns,
    // taken rather than inferred — a type that reads live has nothing here to
    // draw even though the grant is real.
    if (!entry || entry.previewable !== true) continue;

    const ownerUserId = str(grant?.owner_user_id);
    if (!ownerUserId) continue;

    const canonicalType = str(entry.id);
    const key = `${ownerUserId}:${canonicalType}`;
    if (byKey.has(key)) continue;

    byKey.set(key, {
      key,
      ownerUserId,
      displayName: str(grant?.display_name) || str(grant?.email) || ownerUserId,
      resourceType: canonicalType,
      resourceName: str(entry.name) || canonicalType,
    });
  }

  return [...byKey.values()].sort((a, b) => a.displayName.localeCompare(b.displayName));
}

/**
 * The option a block currently points at, if it is still offered.
 *
 * The stored `resourceType` is resolved through the catalog before it is
 * compared, because it may have been written under a legacy alias while
 * the candidate list is keyed by canonical id. Comparing the raw strings
 * would report a working widget as broken — the same alias mismatch this
 * module exists to avoid, just read from the other side.
 */
export function candidateKeyForBlock(
  blockProps: Record<string, unknown>,
  catalog: CatalogEntry[],
  candidates: ShareCandidate[],
): string {
  const owner = str(blockProps?.friendUserId);
  if (!owner) return "";
  const stored = str(blockProps?.resourceType) || "google_calendar";
  const canonical = str(indexCatalog(catalog).get(stored)?.id) || stored;
  const key = `${owner}:${canonical}`;
  return candidates.some((c) => c.key === key) ? key : "";
}

/** True when the block points at an owner but that target is no longer offered. */
export function blockTargetIsGone(
  blockProps: Record<string, unknown>,
  catalog: CatalogEntry[],
  candidates: ShareCandidate[],
): boolean {
  return (
    str(blockProps?.friendUserId).length > 0 &&
    candidateKeyForBlock(blockProps, catalog, candidates) === ""
  );
}
