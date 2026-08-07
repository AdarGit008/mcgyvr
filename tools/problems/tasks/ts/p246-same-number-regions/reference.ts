export function labelValueRegions(grid: number[][]): any {
  if (!Array.isArray(grid) || grid.length === 0) {
    throw new Error("the grid must hold at least one row");
  }
  let width = -1;
  for (const row of grid) {
    if (!Array.isArray(row) || row.length === 0) {
      throw new Error("every row must be a list holding at least one square");
    }
    if (width === -1) width = row.length;
    if (row.length !== width) {
      throw new Error("the rows are not all of one length");
    }
    for (const square of row) {
      if (typeof square !== "number" || !Number.isInteger(square)) {
        throw new Error("every square must be a whole number");
      }
    }
  }
  const height = grid.length;
  const map: number[][] = [];
  for (let r = 0; r < height; r++) map.push(new Array(width).fill(0));
  const sizes: number[] = [];
  const values: number[] = [];
  let next = 0;
  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      if (map[r][c] !== 0) continue;
      next += 1;
      const held = grid[r][c];
      let count = 0;
      const pending: number[][] = [[r, c]];
      map[r][c] = next;
      while (pending.length > 0) {
        const spot = pending.pop();
        if (spot === undefined) break;
        const [row, col] = spot;
        count += 1;
        const steps = [
          [row - 1, col],
          [row + 1, col],
          [row, col - 1],
          [row, col + 1],
        ];
        for (const [nr, nc] of steps) {
          if (nr < 0 || nr >= height || nc < 0 || nc >= width) continue;
          if (map[nr][nc] !== 0) continue;
          if (grid[nr][nc] !== held) continue;
          map[nr][nc] = next;
          pending.push([nr, nc]);
        }
      }
      sizes.push(count);
      values.push(held);
    }
  }
  return { map, sizes, values };
}
