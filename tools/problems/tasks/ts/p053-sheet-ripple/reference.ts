export function changedCells(
  cells: Record<string, string>,
  name: string,
  replacement: string,
): string[] {
  if (!(name in cells)) {
    throw new Error(`unknown cell ${name}`);
  }

  const evaluate = (sheet: Record<string, string>): Record<string, number> => {
    const values: Record<string, number> = {};
    const valueOf = (cell: string): number => {
      if (!(cell in values)) {
        const raw = sheet[cell];
        if (raw.startsWith("=")) {
          let sum = 0;
          for (const part of raw.slice(1).split("+")) {
            sum += valueOf(part.trim());
          }
          values[cell] = sum;
        } else {
          values[cell] = Number.parseInt(raw.trim(), 10);
        }
      }
      return values[cell];
    };
    for (const cell of Object.keys(sheet)) {
      valueOf(cell);
    }
    return values;
  };

  const before = evaluate(cells);
  const after = evaluate({ ...cells, [name]: replacement });
  return Object.keys(cells)
    .filter((cell) => before[cell] !== after[cell])
    .sort();
}
