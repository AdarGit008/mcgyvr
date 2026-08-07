export function chainTransforms(grid: number[][], steps: string[]): number[][] {
  if (grid.length === 0) {
    throw new Error("grid has no rows");
  }
  const width = grid[0].length;
  for (const row of grid) {
    if (row.length !== width) {
      throw new Error("rows differ in length");
    }
  }
  const diag = (g: number[][]): number[][] =>
    g[0].map((_, column) => g.map((row) => row[column]));
  let current = grid.map((row) => [...row]);
  for (const step of steps) {
    if (step === "cw") {
      current = diag([...current].reverse());
    } else if (step === "ccw") {
      current = diag(current).reverse();
    } else if (step === "mirror") {
      current = current.map((row) => [...row].reverse());
    } else if (step === "flip") {
      current = [...current].reverse();
    } else if (step === "diag") {
      current = diag(current);
    } else {
      throw new Error(`unknown step ${step}`);
    }
  }
  return current;
}
