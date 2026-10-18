import { describe, expect, it } from "vitest";
import {
  layoutModeOf,
  parseUiLayout,
  withLayoutMode,
} from "./layoutMode";
import type { UiBlock, UiLayout } from "./types";

function block(id: string, grid: { x: number; y: number; w: number; h: number }): UiBlock {
  return { id, type: "markdown", grid, props: { title: id } };
}

function layout(
  mode: "grid" | "canvas",
  blocks: UiBlock[],
  extra: Partial<UiLayout> = {}
): UiLayout {
  return { version: 1, mode, blocks, ...extra };
}

describe("withLayoutMode dual persistence", () => {
  it("keeps canvas positions when returning from grid", () => {
    const canvasLayout = layout("canvas", [
      block("a", { x: 3, y: 5, w: 4, h: 3 }),
      block("b", { x: 10, y: 2, w: 2, h: 2 }),
    ], { canvas: { zoom: 1.25, panX: 40, panY: -10 } });

    const asGrid = withLayoutMode(canvasLayout, "grid");
    expect(layoutModeOf(asGrid)).toBe("grid");
    expect(asGrid.canvas).toBeUndefined();
    expect(asGrid.mode_layouts?.canvas?.blocks.find((b) => b.id === "a")?.grid).toEqual({
      x: 3,
      y: 5,
      w: 4,
      h: 3,
    });

    const back = withLayoutMode(asGrid, "canvas");
    expect(layoutModeOf(back)).toBe("canvas");
    expect(back.blocks.find((b) => b.id === "a")?.grid).toEqual({ x: 3, y: 5, w: 4, h: 3 });
    expect(back.blocks.find((b) => b.id === "b")?.grid).toEqual({ x: 10, y: 2, w: 2, h: 2 });
    expect(back.canvas).toMatchObject({ zoom: 1.25, panX: 40, panY: -10 });
  });

  it("keeps grid positions when returning from canvas", () => {
    const gridLayout = layout("grid", [
      block("a", { x: 0, y: 0, w: 6, h: 2 }),
      block("b", { x: 6, y: 0, w: 6, h: 2 }),
    ]);

    const asCanvas = withLayoutMode(gridLayout, "canvas");
    // Move on canvas
    const moved: UiLayout = {
      ...asCanvas,
      blocks: asCanvas.blocks.map((b) =>
        b.id === "a" ? { ...b, grid: { x: 8, y: 9, w: 6, h: 2 } } : b
      ),
    };

    const back = withLayoutMode(moved, "grid");
    expect(back.blocks.find((b) => b.id === "a")?.grid).toEqual({ x: 0, y: 0, w: 6, h: 2 });
    expect(back.blocks.find((b) => b.id === "b")?.grid).toEqual({ x: 6, y: 0, w: 6, h: 2 });
  });

  it("carries new blocks into the other mode", () => {
    const gridLayout = layout("grid", [block("a", { x: 0, y: 0, w: 4, h: 2 })]);
    const asCanvas = withLayoutMode(gridLayout, "canvas");
    const withNew: UiLayout = {
      ...asCanvas,
      blocks: [...asCanvas.blocks, block("newbie", { x: 2, y: 4, w: 3, h: 2 })],
    };
    const back = withLayoutMode(withNew, "grid");
    expect(back.blocks.map((b) => b.id).sort()).toEqual(["a", "newbie"]);
    expect(back.blocks.find((b) => b.id === "newbie")?.grid.w).toBe(3);
  });

  it("round-trips mode_layouts through parseUiLayout", () => {
    const start = layout("canvas", [block("a", { x: 1, y: 2, w: 3, h: 4 })], {
      canvas: { zoom: 0.8, panX: 1, panY: 2 },
    });
    const switched = withLayoutMode(start, "grid");
    const parsed = parseUiLayout(JSON.parse(JSON.stringify(switched)));
    expect(parsed).not.toBeNull();
    const restored = withLayoutMode(parsed!, "canvas");
    expect(restored.blocks[0]?.grid).toEqual({ x: 1, y: 2, w: 3, h: 4 });
    expect(restored.canvas?.zoom).toBe(0.8);
  });

  it("is a no-op when mode is unchanged", () => {
    const gridLayout = layout("grid", [block("a", { x: 0, y: 0, w: 4, h: 2 })]);
    expect(withLayoutMode(gridLayout, "grid")).toBe(gridLayout);
  });
});
