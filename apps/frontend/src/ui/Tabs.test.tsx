import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TabPanel, Tabs } from "./Tabs";

/**
 * The seven strips this primitive replaced all worked with a mouse and stopped
 * there: five of them never said they were tabs, and not one moved on an arrow
 * key — which is the whole interaction the tab pattern is defined by (WCAG
 * 2.1.1). A strip that looks right and cannot be left with the keyboard is the
 * failure mode, so the keys and the id pairing are what gets asserted.
 */

const items = [
  { id: "one", label: "One" },
  { id: "two", label: "Two" },
  { id: "three", label: "Three" },
];

function renderTabs(props: Partial<React.ComponentProps<typeof Tabs>> = {}) {
  const onChange = vi.fn();
  render(<Tabs items={items} value="one" onChange={onChange} ariaLabel="Sections" {...props} />);
  return onChange;
}

function selected(): string | null {
  return (
    screen
      .getAllByRole("tab")
      .find((tab) => tab.getAttribute("aria-selected") === "true")
      ?.textContent ?? null
  );
}

describe("Tabs", () => {
  it("names the strip and marks exactly one tab selected", () => {
    renderTabs();
    expect(screen.getByRole("tablist")).toHaveAttribute("aria-label", "Sections");
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.filter((tab) => tab.getAttribute("aria-selected") === "true")).toHaveLength(1);
  });

  it("puts the whole strip in one tab stop and the selected tab in it", () => {
    renderTabs();
    expect(screen.getByText("One")).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("Two")).toHaveAttribute("tabindex", "-1");
  });

  it("moves the selection with the arrow keys instead of leaving it stranded", () => {
    const onChange = renderTabs();
    fireEvent.keyDown(screen.getByText("One"), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("two");
  });

  it("wraps at both ends so the keys never dead-end", () => {
    const onChange = renderTabs();
    fireEvent.keyDown(screen.getByText("One"), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("three");
    fireEvent.keyDown(screen.getByText("One"), { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("three");
    fireEvent.keyDown(screen.getByText("One"), { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("one");
  });

  it("steps over a disabled tab rather than selecting it", () => {
    const onChange = renderTabs({
      items: [items[0]!, { ...items[1]!, disabled: true }, items[2]!],
    });
    fireEvent.keyDown(screen.getByText("One"), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("three");
  });

  it("moves focus to the tab it selected, so the keyboard stays on the strip", () => {
    renderTabs({ value: "one", onChange: (id) => void id });
    const two = screen.getByText("Two");
    fireEvent.keyDown(screen.getByText("One"), { key: "ArrowRight" });
    expect(two).toHaveFocus();
  });

  it("pairs each tab with its panel once a group is shared", () => {
    render(
      <>
        <Tabs
          items={items}
          value="two"
          onChange={() => {}}
          ariaLabel="Sections"
          groupId="g"
        />
        <TabPanel id="two" group="g">
          Panel body
        </TabPanel>
      </>
    );
    const tab = screen.getByText("Two");
    const panel = screen.getByRole("tabpanel");
    expect(tab).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", tab.id);
    expect(selected()).toBe("Two");
  });

  it("leaves aria-controls out when no panel was ever paired", () => {
    renderTabs();
    expect(screen.getByText("One")).not.toHaveAttribute("aria-controls");
  });
});