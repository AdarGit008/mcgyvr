export function quarterSpin(grid: number[][], turns: number): number[][] {
  let result = grid.map((row) => [...row]);
  for (let t = 0; t < turns % 4; t++) {
    const rows = result.length;
    const cols = rows === 0 ? 0 : result[0].length;
    const next: number[][] = [];
    for (let c = 0; c < cols; c++) {
      const row: number[] = [];
      for (let r = rows - 1; r >= 0; r--) {
        row.push(result[r][c]);
      }
      next.push(row);
    }
    result = next;
  }
  return result;
}
