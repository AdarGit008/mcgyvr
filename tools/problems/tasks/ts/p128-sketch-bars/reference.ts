export function sketchBars(values: number[], budget: number): string[] {
  if (values.length === 0) {
    throw new Error("no values to sketch");
  }
  if (!Number.isInteger(budget) || budget < 1) {
    throw new Error("budget must be a positive integer");
  }
  for (const v of values) {
    if (!Number.isInteger(v) || v < 0) {
      throw new Error("values must be non-negative integers");
    }
  }
  const top = Math.max(...values);
  return values.map((v) => {
    let cells = 0;
    if (top > 0 && v > 0) {
      cells = Math.floor((2 * v * budget + top) / (2 * top));
      if (cells === 0) {
        cells = 1;
      }
    }
    return "#".repeat(cells) + ".".repeat(budget - cells);
  });
}
