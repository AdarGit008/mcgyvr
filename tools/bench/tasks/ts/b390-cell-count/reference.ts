export function cellCount(grid: number[][], value: number): number {
  let found = 0;
  for (const row of grid) {
    for (const cell of row) {
      if (cell === value) {
        found += 1;
      }
    }
  }
  return found;
}
