export function tallyColumn(table: number[][], column: number): Record<string, number> {
  if (!Array.isArray(table) || table.length === 0) {
    throw new Error("table must hold at least one row");
  }
  const width = table[0].length;
  if (!Number.isInteger(column) || column < 0 || column >= width) {
    throw new Error("column index is outside the rows");
  }
  let count = 0;
  let total = 0;
  let low = Infinity;
  let high = -Infinity;
  for (const row of table) {
    if (row.length !== width) {
      throw new Error("rows must share one length");
    }
    const value = row[column];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error("cells in the column must be numbers");
    }
    count += 1;
    total += value;
    if (value < low) low = value;
    if (value > high) high = value;
  }
  return { count, total, low, high };
}
