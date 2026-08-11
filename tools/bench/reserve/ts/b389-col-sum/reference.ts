export function colSum(grid: number[][], column: number): number {
  let total = 0;
  for (const row of grid) {
    if (column < row.length) {
      total += row[column];
    }
  }
  return total;
}
