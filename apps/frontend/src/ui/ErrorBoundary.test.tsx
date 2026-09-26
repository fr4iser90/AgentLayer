import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterAll, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

/**
 * The boundary is tested against a planted render exception, because that is the
 * only input it has. Three things had to be proven, in this order:
 *
 * - the crash is caught and the sibling outside keeps rendering — the point of
 *   the boundary is that one broken area does not take the shell with it;
 * - the caught message reaches the screen, since the fallback is the only place
 *   a user can read what broke;
 * - it lets go. A boundary that cannot recover turns a one-off render error into
 *   a dead page, so both ways out are asserted: the retry action and a changed
 *   `resetKey`, which is what the route does around it in `AppLayout`.
 *
 * `react-i18next` is mocked so the fallback reads back its keys — asserting on
 * "Try again" would pass even if the component asked for a different string.
 */
const tMock = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: tMock.t, i18n: { language: "en" } }),
}));

let explode = false;

function Exploding() {
  if (explode) throw new Error("planted render exception");
  return <p>the area is fine</p>;
}

// React 18 replays every caught error on the window as well — `invokeGuardedCallback`
// does that on purpose so a debugger stops on the original stack. In the app that is
// right; in Vitest the replay reaches jsdom as an uncaught error and fails whichever
// test happens to be running. Cancelling the window event silences the replay only:
// `componentDidCatch` still runs, and its console line is asserted below. Registered
// once for the file because the replay can land after the test that caused it.
const swallow = (event: ErrorEvent) => event.preventDefault();
window.addEventListener("error", swallow, { capture: true });
afterAll(() => window.removeEventListener("error", swallow, { capture: true }));

function silenceConsoleError() {
  return vi.spyOn(console, "error").mockImplementation(() => {});
}

describe("ErrorBoundary", () => {
  it("renders children while nothing throws", () => {
    explode = false;
    render(
      <ErrorBoundary area="chat">
        <Exploding />
      </ErrorBoundary>
    );
    expect(screen.getByText("the area is fine")).toBeInTheDocument();
  });

  it("catches a planted render exception and keeps the rest of the tree", () => {
    explode = true;
    const spy = silenceConsoleError();
    render(
      <div>
        <nav>the navigation</nav>
        <ErrorBoundary area="chat">
          <Exploding />
        </ErrorBoundary>
      </div>
    );
    expect(screen.getByText("the navigation")).toBeInTheDocument();
    expect(screen.getByText("errorBoundary.title")).toBeInTheDocument();
    expect(screen.getByText("planted render exception")).toBeInTheDocument();
    expect(screen.queryByText("the area is fine")).not.toBeInTheDocument();
    expect(spy.mock.calls.some((c) => c[0] === "[ErrorBoundary] chat")).toBe(true);
  });

  it("gives the area back on retry", () => {
    explode = true;
    silenceConsoleError();
    render(
      <ErrorBoundary area="chat">
        <Exploding />
      </ErrorBoundary>
    );
    expect(screen.getByText("errorBoundary.title")).toBeInTheDocument();
    // The bug goes away (a reload brought new data); the retry has to be enough.
    explode = false;
    fireEvent.click(screen.getByText("errorBoundary.retry"));
    expect(screen.getByText("the area is fine")).toBeInTheDocument();
    expect(screen.queryByText("errorBoundary.title")).not.toBeInTheDocument();
  });

  it("lets go when the reset key changes, without being asked", () => {
    explode = true;
    silenceConsoleError();
    function Harness() {
      const [route, setRoute] = useState("/chat");
      return (
        <div>
          <button type="button" onClick={() => setRoute("/settings")}>
            navigate
          </button>
          <ErrorBoundary area="page" resetKey={route}>
            <Exploding />
          </ErrorBoundary>
        </div>
      );
    }
    render(<Harness />);
    expect(screen.getByText("errorBoundary.title")).toBeInTheDocument();
    explode = false;
    fireEvent.click(screen.getByText("navigate"));
    expect(screen.getByText("the area is fine")).toBeInTheDocument();
  });
});