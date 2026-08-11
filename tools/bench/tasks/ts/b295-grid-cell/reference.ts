export function cellName(row: number, column: number): string {
  return String.fromCharCode(65 + column) + String(row + 1);
}

export function gridCells(rows: number, columns: number): string[] {
  const names: string[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      names.push(cellName(row, column));
    }
  }
  return names;
}
