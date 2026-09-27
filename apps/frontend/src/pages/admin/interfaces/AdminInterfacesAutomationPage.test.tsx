import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AdminInterfacesAutomationPage } from "./AdminInterfacesAutomationPage";

/**
 * What plugin cron got when its page went away.
 *
 * `/admin/scheduled-jobs` was deleted — a nav leaf, a route and a stub that said
 * there is no API to operate those jobs through. The stub's only content was the
 * explanation, so it was moved here rather than dropped: whoever reads the
 * scheduler fields is the reader who needs to be told those jobs are not that.
 *
 * `t` returns the key, so this pins the keys being asked for and not their text.
 */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

// The settings panel behind the note is the section's own concern; its loading
// branch keeps this file about what the page renders around it.
vi.mock("../../../features/admin/operatorSettings/OperatorSettingsProvider", () => ({
  useOperatorSettings: () => ({ loading: true })
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminInterfacesAutomationPage />
    </MemoryRouter>
  );
}

describe("the plugin-cron note on the automation page", () => {
  it("says the registry is where those jobs come from", () => {
    renderPage();
    expect(screen.getByText("admin:pluginCronTitle")).toBeInTheDocument();
    expect(screen.getByText("admin:pluginCronIntro")).toBeInTheDocument();
    expect(screen.getByText("admin:pluginCronLlmNote")).toBeInTheDocument();
    expect(screen.getByText("admin:pluginCronNoApi")).toBeInTheDocument();
  });

  it("points at no route that has been removed", () => {
    const { container } = renderPage();
    // The deleted page left no redirect, so a stale link here would land on a
    // blank route with nothing but the rail to get back by.
    const targets = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href") ?? "");
    expect(targets.filter((href) => href.endsWith("/scheduled-jobs"))).toEqual([]);
  });
});