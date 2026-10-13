import { describe, expect, it } from "vitest";
import {
  blockTargetIsGone,
  buildShareCandidates,
  candidateKeyForBlock,
} from "./shareWidgetCandidates";

/**
 * The picker decides what a widget may be pointed at, so its two rules are
 * worth pinning separately from the modal:
 *
 *  - a grant is not a preview. Only projection-backed types are offered,
 *    because a widget pointed at a live-read type draws an empty box and
 *    reads as a broken share rather than an absent one;
 *  - the catalog is matched by canonical id *and* alias, and the
 *    candidate always reports the canonical id. Both directions of that
 *    mismatch have already caused defects here, so neither half gets to
 *    rely on the caller having normalised something.
 */

const CATALOG = [
  {
    id: "google_calendar",
    name: "google calendar",
    aliases: ["calendar"],
    previewable: true,
  },
  {
    id: "dashboard",
    name: "dashboard",
    aliases: [],
    previewable: false,
  },
  {
    id: "collection",
    name: "collection",
    aliases: ["list"],
    previewable: true,
  },
];

const GRANT = {
  owner_user_id: "11111111-1111-1111-1111-111111111111",
  resource_type: "google_calendar",
  display_name: "Anna Nord",
  email: "anna@nord.example",
};

describe("buildShareCandidates", () => {
  it("offers a granted, projection-backed resource", () => {
    const out = buildShareCandidates([GRANT], CATALOG);
    expect(out).toHaveLength(1);
    expect(out[0]).toEqual({
      key: `${GRANT.owner_user_id}:google_calendar`,
      ownerUserId: GRANT.owner_user_id,
      displayName: "Anna Nord",
      resourceType: "google_calendar",
      resourceName: "google calendar",
    });
  });

  it("does not offer a type with no preview even though the grant is real", () => {
    // A dashboard grant is perfectly valid and does nothing here: the
    // widget has nothing to draw. Offering it would produce an empty box
    // that looks like a failure.
    const out = buildShareCandidates([{ ...GRANT, resource_type: "dashboard" }], CATALOG);
    expect(out).toEqual([]);
  });

  it("resolves a grant written under the legacy alias and reports the canonical id", () => {
    const out = buildShareCandidates([{ ...GRANT, resource_type: "calendar" }], CATALOG);
    expect(out).toHaveLength(1);
    // Not "calendar" — the widget would then ask for a type the catalog
    // does not list, and the option it came from would be unfindable.
    expect(out[0].resourceType).toBe("google_calendar");
    expect(out[0].key).toBe(`${GRANT.owner_user_id}:google_calendar`);
  });

  it("collapses the alias and canonical spellings of one grant into a single option", () => {
    const out = buildShareCandidates(
      [{ ...GRANT, resource_type: "calendar" }, { ...GRANT, resource_type: "google_calendar" }],
      CATALOG,
    );
    expect(out).toHaveLength(1);
  });

  it("lists the same resource shared by two friends as two options", () => {
    const other = {
      ...GRANT,
      owner_user_id: "22222222-2222-2222-2222-222222222222",
      display_name: "Zoe West",
    };
    const out = buildShareCandidates([GRANT, other], CATALOG);
    expect(out.map((c) => c.displayName)).toEqual(["Anna Nord", "Zoe West"]);
  });

  it("falls back to the email, then the id, when a friend has no display name", () => {
    const noName = { ...GRANT, display_name: "" };
    expect(buildShareCandidates([noName], CATALOG)[0].displayName).toBe("anna@nord.example");
    const noContact = { owner_user_id: "33333333-3333-3333-3333-333333333333", resource_type: "calendar" };
    expect(buildShareCandidates([noContact], CATALOG)[0].displayName).toBe(
      "33333333-3333-3333-3333-333333333333",
    );
  });

  it("ignores a grant with no owner rather than offering an empty target", () => {
    expect(buildShareCandidates([{ resource_type: "calendar" }], CATALOG)).toEqual([]);
  });

  it("ignores a grant for a type the catalog does not know at all", () => {
    // Grantable is not readable (§1.4): a type with no adapter has no
    // entry, and offering it would promise a preview that cannot exist.
    expect(buildShareCandidates([{ ...GRANT, resource_type: "not_a_type" }], CATALOG)).toEqual([]);
  });

  it("treats a missing previewable flag as not previewable", () => {
    const catalog = [{ id: "google_calendar", name: "cal", aliases: [] }];
    expect(buildShareCandidates([GRANT], catalog)).toEqual([]);
  });
});

describe("candidateKeyForBlock", () => {
  const candidates = buildShareCandidates([GRANT], CATALOG);

  it("matches a block already stored with the canonical type", () => {
    expect(
      candidateKeyForBlock({ friendUserId: GRANT.owner_user_id, resourceType: "google_calendar" }, CATALOG, candidates),
    ).toBe(`${GRANT.owner_user_id}:google_calendar`);
  });

  it("matches a block stored with the legacy alias instead of reporting it broken", () => {
    // Read from the other side of the same mismatch: the widget works when
    // pointed at "calendar", so the picker must not claim the target is
    // gone just because the candidate list is keyed canonically.
    expect(
      candidateKeyForBlock({ friendUserId: GRANT.owner_user_id, resourceType: "calendar" }, CATALOG, candidates),
    ).toBe(`${GRANT.owner_user_id}:google_calendar`);
  });

  it("assumes the default type when the block names none", () => {
    expect(candidateKeyForBlock({ friendUserId: GRANT.owner_user_id }, CATALOG, candidates)).toBe(
      `${GRANT.owner_user_id}:google_calendar`,
    );
  });

  it("returns nothing for a block with no owner", () => {
    expect(candidateKeyForBlock({ resourceType: "google_calendar" }, CATALOG, candidates)).toBe("");
  });

  it("returns nothing when the owner is not among the candidates", () => {
    expect(
      candidateKeyForBlock({ friendUserId: "99999999-9999-9999-9999-999999999999" }, CATALOG, candidates),
    ).toBe("");
  });
});

describe("blockTargetIsGone", () => {
  const candidates = buildShareCandidates([GRANT], CATALOG);

  it("is false while the current target is still offered", () => {
    expect(
      blockTargetIsGone({ friendUserId: GRANT.owner_user_id, resourceType: "calendar" }, CATALOG, candidates),
    ).toBe(false);
  });

  it("is true when the owner was once set but is no longer available", () => {
    // The revoke case: the widget still names an owner, so the user needs
    // to be told why it shows nothing, rather than finding an empty picker.
    expect(
      blockTargetIsGone({ friendUserId: "99999999-9999-9999-9999-999999999999" }, CATALOG, candidates),
    ).toBe(true);
  });

  it("is false for a brand-new widget that has never had an owner", () => {
    expect(blockTargetIsGone({}, CATALOG, candidates)).toBe(false);
  });
});
