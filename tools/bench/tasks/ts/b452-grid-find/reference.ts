export function matchAt(
  grid: number[][],
  row: number,
  column: number,
  value: number,
): boolean {
  return grid[row][column] === value;
}

export function gridFind(grid: number[][], value: number): number[] {
  for (let r = 0; r < grid.length; r += 1) {
    for (let c = 0; c < grid[r].length; c += 1) {
      if (matchAt(grid, r, c, value)) {
        return [r, c];
      }
    }
  }
  throw new Error("the value is not in the grid");
}
