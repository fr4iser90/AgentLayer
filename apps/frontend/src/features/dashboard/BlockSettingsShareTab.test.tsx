import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BlockSettingsModal } from "./BlockSettingsModal";
import { apiFetch } from "../../lib/api";
import type { UiBlock } from "./types";

/**
 * The share widget used to be excluded from block configuration outright,
 * so `friendUserId` could only be set by editing layout JSON. These pin
 * the two things that matter about admitting it:
 *
 *  - the picker offers only resources that would actually render, so a
 *    choice cannot produce an empty widget;
 *  - saving without picking does not blank the widget's existing owner.
 *    A mis-click on an empty select should not be able to destroy a
 *    working configuration.
 *
 * Mock identities are stable on purpose: a fresh `useAuth` object each
 * render would re-fire the candidate fetch forever, which hangs the test
 * rather than failing it.
 */
type MockAuthState = { user: unknown; loading: boolean; accessToken: string };
const authState = vi.hoisted<MockAuthState>(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
}));
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } }),
}));
vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

const ANNA = "11111111-1111-1111-1111-111111111111";
const BO = "22222222-2222-2222-2222-222222222222";

const CATALOG = [
  { id: "google_calendar", name: "google calendar", aliases: ["calendar"], previewable: true },
  { id: "dashboard", name: "dashboard", aliases: [], previewable: false },
];

function incoming(shares: unknown[]) {
  api.mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.startsWith("/v1/shares/incoming")) return json({ ok: true, shares });
    if (u.startsWith("/v1/shares/catalog")) return json({ ok: true, resources: CATALOG });
    return json({ ok: true });
  });
}

function json(body: unknown) {
  return { ok: true, json: async () => body, text: async () => "" } as unknown as Response;
}

function shareBlock(props: Record<string, unknown> = {}): UiBlock {
  return {
    id: "block-share-1",
    type: "share_widget",
    grid: { x: 0, y: 0, w: 4, h: 4 },
    props: { title: "Friend share", resourceType: "google_calendar", ...props },
  };
}

async function openShareTab(block: UiBlock) {
  const onSave = vi.fn();
  render(
    <BlockSettingsModal block={block} data={{}} autoSave saving={false} onClose={() => {}} onSave={onSave} />,
  );
  fireEvent.click(await screen.findByText("dashboard:blockSettingsTabShare"));
  return onSave;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("share tab availability", () => {
  it("gives the share widget a share tab", async () => {
    incoming([]);
    render(
      <BlockSettingsModal
        block={shareBlock()}
        data={{}}
        autoSave
        saving={false}
        onClose={() => {}}
        onSave={vi.fn()}
      />,
    );
    expect(await screen.findByText("dashboard:blockSettingsTabShare")).toBeTruthy();
  });

  it("does not give other blocks a share tab", async () => {
    incoming([]);
    render(
      <BlockSettingsModal
        block={{ id: "b2", type: "table", grid: { x: 0, y: 0, w: 4, h: 4 }, props: {} }}
        data={{}}
        autoSave
        saving={false}
        onClose={() => {}}
        onSave={vi.fn()}
      />,
    );
    await screen.findByText("dashboard:blockSettingsTabData");
    expect(screen.queryByText("dashboard:blockSettingsTabShare")).toBeNull();
  });
});

describe("candidate list", () => {
  it("offers only granted resources that have a preview", async () => {
    incoming([
      { owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" },
      { owner_user_id: BO, resource_type: "dashboard", display_name: "Zoe West" },
    ]);
    await openShareTab(shareBlock());

    const select = (await screen.findByLabelText("dashboard:blockSettingsShareTarget")) as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value).filter(Boolean);
    // Bo's dashboard grant is real and useless here — nothing to draw.
    expect(values).toEqual([`${ANNA}:google_calendar`]);
  });

  it("says so when there is nothing to point the widget at", async () => {
    incoming([]);
    await openShareTab(shareBlock());
    expect(await screen.findByText("dashboard:blockSettingsShareNone")).toBeTruthy();
    expect(screen.queryByLabelText("dashboard:blockSettingsShareTarget")).toBeNull();
  });

  it("selects the option the block already points at", async () => {
    incoming([{ owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" }]);
    await openShareTab(shareBlock({ friendUserId: ANNA }));

    const select = (await screen.findByLabelText("dashboard:blockSettingsShareTarget")) as HTMLSelectElement;
    expect(select.value).toBe(`${ANNA}:google_calendar`);
  });

  it("selects a block stored under the legacy alias rather than showing it as gone", async () => {
    incoming([{ owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" }]);
    await openShareTab(shareBlock({ friendUserId: ANNA, resourceType: "calendar" }));

    const select = (await screen.findByLabelText("dashboard:blockSettingsShareTarget")) as HTMLSelectElement;
    expect(select.value).toBe(`${ANNA}:google_calendar`);
    expect(screen.queryByText("dashboard:blockSettingsShareTargetGone")).toBeNull();
  });

  it("warns when the widget points at something no longer available", async () => {
    incoming([]);
    await openShareTab(shareBlock({ friendUserId: BO }));
    expect(await screen.findByText("dashboard:blockSettingsShareTargetGone")).toBeTruthy();
  });
});

describe("saving the share target", () => {
  it("writes the picked owner, name and canonical type", async () => {
    incoming([
      { owner_user_id: ANNA, resource_type: "calendar", display_name: "Anna Nord" },
      { owner_user_id: BO, resource_type: "google_calendar", display_name: "Zoe West" },
    ]);
    const onSave = await openShareTab(shareBlock({ friendUserId: ANNA, friendDisplayName: "Anna Nord" }));

    const select = (await screen.findByLabelText("dashboard:blockSettingsShareTarget")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: `${BO}:google_calendar` } });
    fireEvent.click(screen.getByText("dashboard:blockSettingsSaveAuto"));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect(onSave.mock.calls[0][0]).toMatchObject({
      friendUserId: BO,
      friendDisplayName: "Zoe West",
      resourceType: "google_calendar",
    });
  });

  it("keeps the existing owner when nothing is picked", async () => {
    // The point of the empty option: it must be inert. Clearing the select
    // and saving would otherwise turn a stray click into a widget that
    // shows nothing, with no way to see what it used to point at.
    incoming([{ owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" }]);
    const onSave = await openShareTab(shareBlock({ friendUserId: ANNA, friendDisplayName: "Anna Nord" }));

    const select = (await screen.findByLabelText("dashboard:blockSettingsShareTarget")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByText("dashboard:blockSettingsSaveAuto"));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const saved = onSave.mock.calls[0][0] as Record<string, unknown>;
    expect(saved.friendUserId).toBe(ANNA);
    expect(saved.friendDisplayName).toBe("Anna Nord");
  });

  it("saves the chosen horizon", async () => {
    incoming([{ owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" }]);
    const onSave = await openShareTab(shareBlock({ friendUserId: ANNA }));

    const days = (await screen.findByLabelText("dashboard:blockSettingsShareDays")) as HTMLInputElement;
    expect(days.value).toBe("7");
    fireEvent.change(days, { target: { value: "21" } });
    fireEvent.click(screen.getByText("dashboard:blockSettingsSaveAuto"));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect((onSave.mock.calls[0][0] as Record<string, unknown>).daysAhead).toBe(21);
  });

  it("does not give the share widget a data path it would never read", async () => {
    incoming([{ owner_user_id: ANNA, resource_type: "google_calendar", display_name: "Anna Nord" }]);
    const onSave = await openShareTab(shareBlock({ friendUserId: ANNA }));

    fireEvent.click(screen.getByText("dashboard:blockSettingsSaveAuto"));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect("dataPath" in (onSave.mock.calls[0][0] as Record<string, unknown>)).toBe(false);
  });

  it("still saves the title", async () => {
    incoming([]);
    const onSave = await openShareTab(shareBlock());
    fireEvent.click(screen.getByText("dashboard:blockSettingsTabGeneral"));
    const title = (await screen.findByDisplayValue("Friend share")) as HTMLInputElement;
    fireEvent.change(title, { target: { value: "Annas Schichten" } });
    fireEvent.click(screen.getByText("dashboard:blockSettingsSaveAuto"));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    expect((onSave.mock.calls[0][0] as Record<string, unknown>).title).toBe("Annas Schichten");
  });
});
