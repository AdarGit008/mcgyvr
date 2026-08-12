export function cellAt(
  grid: number[][],
  row: number,
  column: number,
): number {
  if (row < 0 || row >= grid.length) {
    return 0;
  }
  if (column < 0 || column >= grid[row].length) {
    return 0;
  }
  return grid[row][column];
}

export function diagOf(grid: number[][]): number[] {
  const values: number[] = [];
  for (let i = 0; i < grid.length; i += 1) {
    values.push(cellAt(grid, i, i));
  }
  return values;
}
