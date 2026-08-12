/**
 * Pivot a flat list of [row, column, amount] entries into a dense table.
 * Row and column labels are ordered by their descending totals, ties
 * alphabetical; the matrix holds sums with zeros where no entry lands;
 * the margins carry row, column and grand totals, a count of the truly
 * blank cells, and each row's leading column.
 */
export function pivotMargins(entries: [string, string, number][]): {
  rows: string[];
  cols: string[];
  cells: number[][];
  rowTotals: number[];
  colTotals: number[];
  grand: number;
  blanks: number;
  leaders: string[];
} {
  if (!Array.isArray(entries)) {
    throw new Error("entries must be a list");
  }
  const sums = new Map<string, number>();
  const rowSums = new Map<string, number>();
  const colSums = new Map<string, number>();
  for (const entry of entries) {
    if (!Array.isArray(entry) || entry.length !== 3) {
      throw new Error("each entry is a [row, column, amount] triple");
    }
    const [row, col, amount] = entry;
    if (typeof row !== "string" || row === "") {
      throw new Error("row label must be a non-empty string");
    }
    if (typeof col !== "string" || col === "") {
      throw new Error("column label must be a non-empty string");
    }
    if (typeof amount !== "number" || !Number.isInteger(amount)) {
      throw new Error("amount must be an integer");
    }
    const key = JSON.stringify([row, col]);
    sums.set(key, (sums.get(key) ?? 0) + amount);
    rowSums.set(row, (rowSums.get(row) ?? 0) + amount);
    colSums.set(col, (colSums.get(col) ?? 0) + amount);
  }
  const byTotalThenName =
    (totals: Map<string, number>) => (a: string, b: string) => {
      const gap = totals.get(b)! - totals.get(a)!;
      if (gap !== 0) {
        return gap;
      }
      return a < b ? -1 : 1;
    };
  const rows = [...rowSums.keys()].sort(byTotalThenName(rowSums));
  const cols = [...colSums.keys()].sort(byTotalThenName(colSums));
  const cells: number[][] = [];
  const rowTotals: number[] = [];
  const colTotals: number[] = cols.map(() => 0);
  const leaders: string[] = [];
  let grand = 0;
  let blanks = 0;
  for (const row of rows) {
    const line: number[] = [];
    let lineTotal = 0;
    let leadAt = 0;
    cols.forEach((col, index) => {
      const key = JSON.stringify([row, col]);
      if (!sums.has(key)) {
        blanks += 1;
      }
      const value = sums.get(key) ?? 0;
      line.push(value);
      lineTotal += value;
      colTotals[index] += value;
      if (value > line[leadAt]) {
        leadAt = index;
      }
    });
    cells.push(line);
    rowTotals.push(lineTotal);
    leaders.push(cols[leadAt]);
    grand += lineTotal;
  }
  return { rows, cols, cells, rowTotals, colTotals, grand, blanks, leaders };
}
