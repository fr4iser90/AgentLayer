import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ProjectsImportModal } from "./ProjectsImportModal";
import { apiFetch } from "../../lib/api";

/**
 * The import dialog is `max-h-full` and centred, so its height follows its
 * content: while the repository list is in flight the dialog is one line of text
 * tall, and when the list lands the header and the filter row above the body are
 * pushed up as the panel grows. The placeholder is what stops that, so this file
 * pins the height it reserves — `10 x 58` — rather than only that a placeholder
 * exists. A regression back to `<p>Loading</p>` fails the height, not a review.
 */
const authState = vi.hoisted(() => ({
  user: null,
  loading: false,
  accessToken: "tok",
  refresh: async () => true,
}));

vi.mock("../../auth/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));

const api = vi.mocked(apiFetch);

// `release` lets a test hold the repository request open, look at the loading
// branch, and only then let the list arrive.
const gateway = vi.hoisted(() => ({
  repos: [] as unknown[],
  release: null as null | ((value: { ok: boolean; repos: unknown[] }) => void),
}));

const repo = (name: string) => ({
  full_name: `acme/${name}`,
  name,
  html_url: `https://github.com/acme/${name}`,
  clone_url: `https://github.com/acme/${name}.git`,
  default_branch: "main",
  description: "A repository with a description",
  private: false,
});

function openDialog() {
  return render(
    <ProjectsImportModal
      open
      onClose={() => {}}
      auth={{ accessToken: "tok", refresh: async () => true }}
      dashboardId="dash-1"
      onImported={() => {}}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  gateway.repos = [];
  gateway.release = null;
  api.mockImplementation(async () => {
    const body = await new Promise<{ ok: boolean; repos: unknown[] }>((resolve) => {
      gateway.release = resolve;
    });
    return { ok: true, json: async () => body } as unknown as Response;
  });
});

describe("import dialog loading state", () => {
  it("reserves ten repository rows while the list is in flight", () => {
    openDialog();
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("dashboard:loading");
    const rows = status.querySelector("[data-skeleton-rows]");
    // 10 rows x the 58 px pitch of a real row (py-base around a text-sm name
    // and a text-xs description, plus the border and the list's space-y-tight).
    expect(rows?.getAttribute("style")).toContain("min-height: 580px");
  });

  it("gives the reserved height back to the list once the repos land", async () => {
    openDialog();
    expect(screen.getByRole("status").querySelector("[data-skeleton-rows]")).toBeTruthy();

    gateway.repos = [repo("alpha"), repo("beta")];
    await waitFor(() => expect(gateway.release).toBeTruthy());
    gateway.release?.({ ok: true, repos: gateway.repos });

    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(await screen.findByText("acme/alpha")).toBeTruthy();
  });
});