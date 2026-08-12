export function regionTotals(grid: number[][], queries: number[][]): number[] {
  if (!Array.isArray(grid) || grid.length === 0) {
    throw new Error("grid must be a non-empty list of rows");
  }
  const width = Array.isArray(grid[0]) ? grid[0].length : 0;
  if (width === 0) {
    throw new Error("rows must be non-empty lists");
  }
  for (const row of grid) {
    if (!Array.isArray(row) || row.length !== width) {
      throw new Error("rows must all share one length");
    }
    for (const cell of row) {
      if (!Number.isInteger(cell)) {
        throw new Error("cells must be integers");
      }
    }
  }
  const height = grid.length;
  const prefix: number[][] = [];
  for (let r = 0; r <= height; r += 1) {
    prefix.push(new Array(width + 1).fill(0));
  }
  for (let r = 0; r < height; r += 1) {
    for (let c = 0; c < width; c += 1) {
      prefix[r + 1][c + 1] =
        grid[r][c] + prefix[r][c + 1] + prefix[r + 1][c] - prefix[r][c];
    }
  }
  const totals: number[] = [];
  for (const query of queries) {
    if (!Array.isArray(query) || query.length !== 4) {
      throw new Error("a query is [top, left, bottom, right]");
    }
    for (const bound of query) {
      if (!Number.isInteger(bound)) {
        throw new Error("query bounds must be integers");
      }
    }
    const [top, left, bottom, right] = query;
    if (top >= bottom || left >= right) {
      throw new Error("query bounds must name a non-empty block");
    }
    if (top < 0 || left < 0 || bottom > height || right > width) {
      throw new Error("query reaches outside the grid");
    }
    totals.push(
      prefix[bottom][right] -
        prefix[top][right] -
        prefix[bottom][left] +
        prefix[top][left],
    );
  }
  return totals;
}
