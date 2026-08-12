export function countTrails(rows: number, cols: number, blocked: number[][]): number {
  if (!Number.isInteger(rows) || !Number.isInteger(cols) || Math.min(rows, cols) < 1) throw new Error("the floor is at least one cell by one cell");
  const ropes = new Set<string>();
  for (const cell of blocked) {
    if (!Array.isArray(cell) || cell.length !== 2) throw new Error("a roped cell is a row and a column");
    if (!(cell[0] >= 0 && cell[0] < rows && cell[1] >= 0 && cell[1] < cols)) throw new Error("a roped cell lies off the floor");
    ropes.add(`${cell[0]},${cell[1]}`);
  }
  if (ropes.has("0,0") || ropes.has(`${rows - 1},${cols - 1}`)) throw new Error("the entrance and the exit stay open");
  const row: number[] = new Array(cols).fill(0);
  row[0] = 1;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (ropes.has(`${r},${c}`)) row[c] = 0;
      else if (c > 0) row[c] += row[c - 1];
    }
  }
  return row[cols - 1];
}
