export function countStripTilings(width: number): number {
  if (typeof width !== "number" || !Number.isInteger(width) || width < 0) {
    throw new Error("width must be a non-negative whole number");
  }
  let twoBack = 1;
  let oneBack = 1;
  if (width === 0) {
    return twoBack;
  }
  for (let n = 2; n <= width; n++) {
    const here = oneBack + 2 * twoBack;
    twoBack = oneBack;
    oneBack = here;
  }
  return oneBack;
}
