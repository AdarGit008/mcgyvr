export function gridDeterminant(grid: number[][]): number {
  if (!Array.isArray(grid) || grid.length === 0) {
    throw new Error("gridDeterminant expects a grid with at least one row");
  }
  if (grid.length > 3) {
    throw new Error("a grid of four rows or more is out of range");
  }
  for (const row of grid) {
    if (!Array.isArray(row) || row.length !== grid.length) {
      throw new Error("every row must be as long as the grid is tall");
    }
    for (const cell of row) {
      if (typeof cell !== "number" || !Number.isInteger(cell)) {
        throw new Error("every cell must be a whole number");
      }
    }
  }
  if (grid.length === 1) {
    return grid[0][0];
  }
  if (grid.length === 2) {
    return grid[0][0] * grid[1][1] - grid[0][1] * grid[1][0];
  }
  let total = 0;
  for (let column = 0; column < 3; column++) {
    const minor: number[][] = [];
    for (let row = 1; row < 3; row++) {
      minor.push(grid[row].filter((_, index) => index !== column));
    }
    const sign = column % 2 === 0 ? 1 : -1;
    total += sign * grid[0][column] * (minor[0][0] * minor[1][1] - minor[0][1] * minor[1][0]);
  }
  return total;
}
