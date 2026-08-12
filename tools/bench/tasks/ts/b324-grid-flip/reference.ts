export function gridFlip(grid: number[][]): number[][] {
  if (grid.length === 0) {
    return [];
  }
  const flipped: number[][] = [];
  for (let column = 0; column < grid[0].length; column += 1) {
    flipped.push(grid.map((row) => row[column]));
  }
  return flipped;
}
