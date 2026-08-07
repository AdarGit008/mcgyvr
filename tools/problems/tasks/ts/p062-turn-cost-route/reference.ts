export function turnCostRoute(grid: number[][], stepCost: number, turnCost: number): number {
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
  if (!Number.isInteger(stepCost) || stepCost < 1) {
    throw new Error("stepCost must be a positive integer");
  }
  if (!Number.isInteger(turnCost) || turnCost < 0) {
    throw new Error("turnCost must be a non-negative integer");
  }
  const rows = grid.length;
  if (grid[0][0] === 1 || grid[rows - 1][cols - 1] === 1) {
    return -1;
  }
  if (rows === 1 && cols === 1) {
    return 0;
  }
  const moves = [[-1, 0], [1, 0], [0, -1], [0, 1]];
  const dist: number[][][] = grid.map((row) =>
    row.map(() => [Infinity, Infinity, Infinity, Infinity]),
  );
  const queue: number[][] = [];
  for (let d = 0; d < 4; d++) {
    const r = moves[d][0];
    const c = moves[d][1];
    if (r >= 0 && r < rows && c >= 0 && c < cols && grid[r][c] === 0) {
      dist[r][c][d] = stepCost;
      queue.push([r, c, d]);
    }
  }
  while (queue.length > 0) {
    const [r, c, d] = queue.shift()!;
    const here = dist[r][c][d];
    for (let nd = 0; nd < 4; nd++) {
      const nr = r + moves[nd][0];
      const nc = c + moves[nd][1];
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols || grid[nr][nc] === 1) {
        continue;
      }
      const cost = here + stepCost + (nd === d ? 0 : turnCost);
      if (cost < dist[nr][nc][nd]) {
        dist[nr][nc][nd] = cost;
        queue.push([nr, nc, nd]);
      }
    }
  }
  const best = Math.min(...dist[rows - 1][cols - 1]);
  return best === Infinity ? -1 : best;
}
