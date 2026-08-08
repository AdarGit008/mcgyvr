export function numberGridSlots(rows: string[]): Array<Record<string, number>> {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("the rows must be a non-empty list");
  }
  const width = typeof rows[0] === "string" ? rows[0].length : -1;
  for (const row of rows) {
    if (typeof row !== "string") throw new Error("a row must be a string");
    if (row.length === 0) throw new Error("a row must not be empty");
    if (row.length !== width) throw new Error("the rows must be all of one length");
    for (const square of row) {
      if (square !== "." && square !== "#") {
        throw new Error("a square is either open or blocked");
      }
    }
  }
  const open = (row: number, col: number): boolean =>
    row >= 0 &&
    row < rows.length &&
    col >= 0 &&
    col < width &&
    rows[row][col] === ".";

  const found: Array<Record<string, number>> = [];
  let count = 0;
  for (let row = 0; row < rows.length; row++) {
    for (let col = 0; col < width; col++) {
      if (!open(row, col)) continue;
      let across = 0;
      if (!open(row, col - 1)) {
        let run = 0;
        while (open(row, col + run)) run += 1;
        if (run >= 2) across = run;
      }
      let down = 0;
      if (!open(row - 1, col)) {
        let run = 0;
        while (open(row + run, col)) run += 1;
        if (run >= 2) down = run;
      }
      if (across === 0 && down === 0) continue;
      count += 1;
      found.push({ at: count, row, col, across, down });
    }
  }
  return found;
}
