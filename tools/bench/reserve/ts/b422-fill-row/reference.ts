export function blankRow(width: number): number[] {
  if (width < 0) {
    throw new Error("a width cannot be below nothing");
  }
  const row: number[] = [];
  for (let i = 0; i < width; i += 1) {
    row.push(0);
  }
  return row;
}

/** A grid of blank rows, each one its own row. */
export function fillRows(rows: number, width: number): number[][] {
  const grid: number[][] = [];
  for (let i = 0; i < rows; i += 1) {
    grid.push(blankRow(width));
  }
  return grid;
}
