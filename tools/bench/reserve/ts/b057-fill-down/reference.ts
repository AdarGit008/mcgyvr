/** Fill-down for a rectangular grid of strings: blanks inherit from above. */

export function blankCells(rows: string[][]): number {
  let blanks = 0;
  for (const row of rows) {
    blanks += row.filter((cell) => cell === "").length;
  }
  return blanks;
}

export function fillDown(rows: string[][]): string[][] {
  const width = rows.length > 0 ? rows[0].length : 0;
  const carry: string[] = [];
  return rows.map((row) => {
    if (row.length !== width) {
      throw new Error("rows must all share one width");
    }
    return row.map((cell, i) => {
      if (cell !== "") {
        carry[i] = cell;
        return cell;
      }
      if (carry[i] === undefined) {
        throw new Error("a blank cell needs a filled cell above it");
      }
      return carry[i];
    });
  });
}
