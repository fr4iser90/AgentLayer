import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Table, type TableColumn } from "./Table";

/**
 * `Table` replaces eleven hand-drawn tables whose differences were all in the
 * parts nobody looks at once a table works: what the header does while
 * scrolling, what an empty list says, what a loading list looks like.
 *
 * A rendered table cannot prove the first two by eye, and all three are exactly
 * where the migrated copies diverged — so each gets an assertion here rather
 * than a screenshot in a review.
 */

interface Row {
  id: number;
  name: string;
  used: number;
}

const columns: Array<TableColumn<Row>> = [
  { key: "name", header: "Name", render: (r) => r.name },
  {
    key: "used",
    header: "Used",
    align: "right",
    width: "9rem",
    render: (r) => r.used,
  },
];

const rows: Row[] = [
  { id: 1, name: "billing", used: 12 },
  { id: 2, name: "support", used: 340 },
];

function renderTable(
  props: Partial<React.ComponentProps<typeof Table<Row>>> = {}
) {
  return render(
    <Table columns={columns} rows={rows} rowKey={(r) => r.id} {...props} />
  );
}

describe("Table", () => {
  it("marks every header cell as a column header", () => {
    renderTable();
    const headers = screen.getAllByRole("columnheader");
    expect(headers).toHaveLength(2);
    expect(headers[0]).toHaveTextContent("Name");
    expect(headers[1]).toHaveTextContent("Used");
  });

  it("renders one row per entry through the column renderers", () => {
    renderTable();
    const body = screen.getAllByRole("row");
    // One header row plus the data rows.
    expect(body).toHaveLength(3);
    expect(screen.getByText("billing")).toBeInTheDocument();
    expect(screen.getByText("340")).toBeInTheDocument();
  });

  it("spans the empty slot across every column instead of a stray dash", () => {
    renderTable({ rows: [], empty: "Nothing scheduled yet" });
    const cell = screen.getByText("Nothing scheduled yet");
    expect(cell).toHaveAttribute("colspan", "2");
    // Header row plus the one spanning row — no leftover placeholder cells.
    expect(screen.getAllByRole("row")).toHaveLength(2);
  });

  it("shows skeleton rows while loading and keeps the empty text out", () => {
    renderTable({ rows: [], loading: true, empty: <span>Nothing at all</span> });
    expect(screen.queryByText("Nothing at all")).not.toBeInTheDocument();
    // The region carrying the table is what assistive tech reads as busy.
    expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "true");
  });

  it("pins the header by default and lets a caller opt out", () => {
    const { rerender } = renderTable();
    expect(screen.getAllByRole("columnheader")[0]).toHaveClass("sticky", "top-0");
    rerender(
      <Table
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        stickyHeader={false}
      />
    );
    expect(screen.getAllByRole("columnheader")[0]).not.toHaveClass("sticky");
  });

  it("carries the density decision onto the cells", () => {
    renderTable({ density: "compact" });
    expect(screen.getByText("billing")).toHaveClass("py-tight");
    expect(screen.getAllByRole("columnheader")[0]).toHaveClass("py-tight");
  });

  it("keeps the header and cell paddings off raw values", () => {
    renderTable();
    expect(screen.getAllByRole("columnheader")[0]).toHaveClass(
      "px-soft",
      "py-base"
    );
    expect(screen.getByText("support")).toHaveClass("px-soft", "py-base");
  });

  it("aligns a numeric column right and gives it the declared width", () => {
    renderTable();
    const numeric = screen.getByText("Used");
    expect(numeric).toHaveClass("text-right");
    expect(numeric).toHaveStyle({ width: "9rem" });
  });
});