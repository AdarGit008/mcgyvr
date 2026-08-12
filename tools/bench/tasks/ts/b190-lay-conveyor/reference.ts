/** Lay a straight eastward conveyor run across a factory floor plan. */
export function layConveyor(floor: string[], row: number, col: number, length: number): string[] {
  if (row < 0 || row >= floor.length) {
    throw new Error("the run starts off the plan");
  }
  const cells = floor[row].split("");
  if (col < 0 || col + length > cells.length) {
    throw new Error("the run would pass the last column");
  }
  for (let at = col; at < col + length; at++) {
    if (cells[at] !== ".") {
      throw new Error("the run covers a cell that is not open");
    }
  }
  for (let at = col; at < col + length; at++) {
    cells[at] = "=";
  }
  const laid = floor.slice();
  laid[row] = cells.join("");
  return laid;
}
