export function latticeRouteCount(grid: number[][]): number {
  if (!Array.isArray(grid) || grid.length === 0) {
    throw new Error("grid must be a non-empty array of rows");
  }
  const cols = Array.isArray(grid[0]) ? grid[0].length : 0;
  for (const row of grid) {
    if (!Array.isArray(row) || row.length !== cols || cols === 0) {
      throw new Error("grid rows must be equal-length non-empty arrays");
    }
    for (const cell of row) {
      if (cell !== 0 && cell !== 1) {
        throw new Error("cells must be 0 or 1");
      }
    }
  }
  const rows = grid.length;
  if (grid[0][0] === 1 || grid[rows - 1][cols - 1] === 1) {
    return 0;
  }
  const routes: number[][] = grid.map((row) => row.map(() => 0));
  routes[0][0] = 1;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if ((r === 0 && c === 0) || grid[r][c] === 1) {
        continue;
      }
      const fromAbove = r > 0 ? routes[r - 1][c] : 0;
      const fromLeft = c > 0 ? routes[r][c - 1] : 0;
      routes[r][c] = fromAbove + fromLeft;
    }
  }
  return routes[rows - 1][cols - 1];
}
