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

  it("gives the table the declared minimum width", () => {
    const { container } = renderTable({ minWidth: "840px" });
    // The floor is what keeps eight columns from squeezing the name column to
    // three characters; without it the wrapper has nothing to scroll.
    expect(container.querySelector("table")).toHaveStyle({ minWidth: "840px" });
  });

  it("puts rowClassName on the row it names and keeps the row chrome", () => {
    renderTable({ rowClassName: (r) => (r.used > 100 ? "bg-success-subtle" : undefined) });
    const body = screen.getAllByRole("row").slice(1);
    expect(body).toHaveLength(2);
    expect(body[1]).toHaveClass("bg-success-subtle");
    expect(body[0]).not.toHaveClass("bg-success-subtle");
    expect(body[1]).toHaveClass("border-b", "hover:bg-white/[0.03]");
  });

  it("draws rowDetail as one row spanning every column, only where there is detail", () => {
    renderTable({
      rowDetail: (r) => (r.id === 1 ? <span>diagnostics</span> : null),
    });
    // Header + both data rows + the single detail row.
    const body = screen.getAllByRole("row").slice(1);
    expect(body).toHaveLength(3);
    const detail = screen.getByText("diagnostics");
    const detailCell = detail.parentElement as HTMLTableCellElement;
    expect(detailCell.tagName).toBe("TD");
    expect(detailCell.colSpan).toBe(columns.length);
    // The detail follows the record it belongs to instead of landing at the end
    // of the table — the row it explains has to stay above it.
    expect(body[1].contains(detail)).toBe(true);
    expect(body[0].contains(detail)).toBe(false);
    expect(body[2].textContent).toContain("support");
    expect(body[2].querySelectorAll("td")).toHaveLength(columns.length);
  });

  it("does not draw detail rows while loading", () => {
    renderTable({ loading: true, rowDetail: () => <span>diagnostics</span> });
    expect(screen.queryByText("diagnostics")).not.toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(2);
  });
});