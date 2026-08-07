const MARK_LIMIT = 1000000000;

function readSheet(
  sheet: number[][],
  rows: number,
  cols: number,
  into: Map<string, number>,
): void {
  if (!Array.isArray(sheet)) {
    throw new Error("a sheet must be a list");
  }
  const here = new Set<string>();
  for (const entry of sheet) {
    if (!Array.isArray(entry) || entry.length !== 3) {
      throw new Error("every entry must be a triple");
    }
    const row = entry[0];
    const col = entry[1];
    const mark = entry[2];
    if (!Number.isInteger(row) || row < 0 || row >= rows) {
      throw new Error("a row index steps outside the shape");
    }
    if (!Number.isInteger(col) || col < 0 || col >= cols) {
      throw new Error("a column index steps outside the shape");
    }
    if (!Number.isInteger(mark) || Math.abs(mark) > MARK_LIMIT) {
      throw new Error("a mark must be a whole number within the limit");
    }
    if (mark === 0) {
      throw new Error("a sheet may not carry a mark of nothing");
    }
    const cell = `${row}:${col}`;
    if (here.has(cell)) {
      throw new Error("a sheet names the same cell twice");
    }
    here.add(cell);
    into.set(cell, (into.get(cell) ?? 0) + mark);
  }
}

export function tripletSumCells(
  left: number[][],
  right: number[][],
  rows: number,
  cols: number,
): number[][] {
  if (!Number.isInteger(rows) || rows < 1 || rows > 10000) {
    throw new Error("rows must be a whole number from 1 through 10000");
  }
  if (!Number.isInteger(cols) || cols < 1 || cols > 10000) {
    throw new Error("cols must be a whole number from 1 through 10000");
  }
  const totals = new Map<string, number>();
  readSheet(left, rows, cols, totals);
  readSheet(right, rows, cols, totals);

  const out: number[][] = [];
  for (const [cell, mark] of totals) {
    if (mark === 0) {
      continue;
    }
    const cut = cell.indexOf(":");
    out.push([Number(cell.slice(0, cut)), Number(cell.slice(cut + 1)), mark + 0]);
  }
  out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return out;
}
