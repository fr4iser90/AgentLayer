import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NavRail } from "./NavRail";
import { adminNav } from "../layout/navModel";

/**
 * The rail's fold, tested where the guard cannot reach.
 *
 * `check-nav-depth.mjs` reads `navModel.ts` and can say the eight interface
 * pages sit below their door. It cannot say what the rail does with that: whether
 * a fold adds a second `nav`, whether the pages it hides are the ones below the
 * door that is on screen, whether the chevron tells a screen reader anything, or
 * whether a click reports the state the reader asked for rather than the one
 * already drawn. `AppShell` owns the value, so the rail owes two things only —
 * render it, and report the next one. That is the whole contract between them,
 * so `Rail` below keeps one value the same way `AppShell` does and the rail is
 * given no state of its own.
 *
 * `react-i18next` is mocked to return the key, so an assertion on
 * `admin:interfacesVoiceTitle` proves the rail asked for that key instead of
 * whatever English happens to say.
 */
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } })
}));

const DOOR = "/admin/interfaces";
const CHILD = "admin:interfacesVoiceTitle";

function Rail({
  path,
  folds: saved = {},
  onFold
}: {
  path: string;
  folds?: Record<string, boolean>;
  onFold?: (to: string, open: boolean) => void;
}) {
  const [folds, setFolds] = useState<Record<string, boolean>>(saved);
  return (
    <MemoryRouter initialEntries={[path]}>
      <NavRail
        surface={adminNav(null)}
        folds={folds}
        onFold={(to, open) => {
          onFold?.(to, open);
          setFolds((current) => ({ ...current, [to]: open }));
        }}
      />
    </MemoryRouter>
  );
}

const foldButton = () => screen.getByRole("button", { name: /nav\.(expand|collapse)Group/ });

describe("a folded group stays one nav", () => {
  it("adds no second nav container", () => {
    const { container } = render(<Rail path={DOOR} />);
    expect(container.querySelectorAll("nav")).toHaveLength(1);
  });

  it("renders the folded pages inside that same nav", () => {
    render(<Rail path={`${DOOR}/voice`} />);
    const nav = screen.getByRole("navigation");
    expect(nav).toContainElement(screen.getByRole("link", { name: "admin:interfacesTitle" }));
    expect(nav).toContainElement(screen.getByRole("link", { name: CHILD }));
  });

  it("keeps the toggle a control beside the link, not a second link", () => {
    // A chevron that navigated would leave the reader somewhere other than where
    // the row said, and a row that both navigates and folds needs the two apart.
    render(<Rail path={DOOR} />);
    expect(foldButton().tagName).toBe("BUTTON");
  });
});

describe("what a fold shows", () => {
  it("is open while the route is below the door", () => {
    render(<Rail path={`${DOOR}/voice`} />);
    expect(screen.getByRole("link", { name: CHILD })).toBeInTheDocument();
    expect(foldButton()).toHaveAttribute("aria-expanded", "true");
  });

  it("is closed while the route is elsewhere", () => {
    render(<Rail path="/admin" />);
    expect(screen.queryByRole("link", { name: CHILD })).toBeNull();
    expect(foldButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("obeys a collapse the reader pressed even from inside the area", () => {
    // The rail may hide pages the reader asked it to hide; it must not hide where
    // they are. The door row stays the active link, so the area keeps its name
    // above the closed group.
    render(<Rail path={`${DOOR}/voice`} folds={{ [DOOR]: false }} />);
    expect(screen.queryByRole("link", { name: CHILD })).toBeNull();
    expect(foldButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "admin:interfacesTitle" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("names the group it opens and links the list it reveals", () => {
    render(<Rail path="/admin" />);
    const closed = foldButton();
    expect(closed).toHaveAccessibleName("nav.expandGroup");
    expect(closed).not.toHaveAttribute("aria-controls");
    fireEvent.click(closed);
    const open = foldButton();
    expect(open).toHaveAccessibleName("nav.collapseGroup");
    const listId = open.getAttribute("aria-controls");
    expect(listId).toBeTruthy();
    expect(document.getElementById(listId ?? "")).toContainElement(
      screen.getByRole("link", { name: CHILD })
    );
  });
});

describe("a click reports the next fold, not the drawn one", () => {
  it("closing a group the reader is inside still says false", () => {
    // The default-open rule lives in the rail, the saved value in `AppShell`. If
    // the rail sent back what it drew instead of what was asked, collapsing from
    // inside the area would look like a no-op and the chevron would seem broken.
    const onFold = vi.fn();
    render(<Rail path={`${DOOR}/voice`} onFold={onFold} />);
    fireEvent.click(foldButton());
    expect(onFold).toHaveBeenCalledWith(DOOR, false);
  });

  it("opening a closed group says true", () => {
    const onFold = vi.fn();
    render(<Rail path="/admin" onFold={onFold} />);
    fireEvent.click(foldButton());
    expect(onFold).toHaveBeenCalledWith(DOOR, true);
  });
});

describe("a fold only stands on a door", () => {
  it("one chevron for the rail's one door", () => {
    // Every leaf growing a chevron is what a model that mistakes a fold for a
    // per-link control produces; it also means the count here tracks the model.
    render(<Rail path="/admin" />);
    expect(screen.getAllByRole("button", { name: /nav\.(expand|collapse)Group/ })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "admin:toolsRegistryTitle" })).toBeInTheDocument();
  });
});