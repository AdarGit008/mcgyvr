export function rowSums(grid: number[][]): number[] {
  const totals: number[] = [];
  for (const row of grid) {
    let total = 0;
    for (const value of row) {
      total += value;
    }
    totals.push(total);
  }
  return totals;
}
