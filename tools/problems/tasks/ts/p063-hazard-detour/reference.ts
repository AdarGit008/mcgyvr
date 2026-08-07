export function hazardDetour(grid: number[][], start: number[], goal: number[]): number {
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
  for (const point of [start, goal]) {
    if (
      !Array.isArray(point) ||
      point.length !== 2 ||
      !Number.isInteger(point[0]) ||
      !Number.isInteger(point[1]) ||
      point[0] < 0 ||
      point[0] >= rows ||
      point[1] < 0 ||
      point[1] >= cols
    ) {
      throw new Error("start and goal must be in-bounds [row, column] pairs");
    }
  }
  const unsafe = (r: number, c: number): boolean => {
    if (grid[r][c] === 1) {
      return true;
    }
    for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const ar = r + dr;
      const ac = c + dc;
      if (ar >= 0 && ar < rows && ac >= 0 && ac < cols && grid[ar][ac] === 1) {
        return true;
      }
    }
    return false;
  };
  if (unsafe(start[0], start[1]) || unsafe(goal[0], goal[1])) {
    return -1;
  }
  if (start[0] === goal[0] && start[1] === goal[1]) {
    return 0;
  }
  const seen = new Set<string>([start[0] + "," + start[1]]);
  const queue: number[][] = [[start[0], start[1], 0]];
  while (queue.length > 0) {
    const [r, c, steps] = queue.shift()!;
    for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) {
        continue;
      }
      if (unsafe(nr, nc) || seen.has(nr + "," + nc)) {
        continue;
      }
      if (nr === goal[0] && nc === goal[1]) {
        return steps + 1;
      }
      seen.add(nr + "," + nc);
      queue.push([nr, nc, steps + 1]);
    }
  }
  return -1;
}
