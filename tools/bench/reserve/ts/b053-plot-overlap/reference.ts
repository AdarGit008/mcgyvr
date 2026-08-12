export function plotOverlap(a: number[], b: number[]): number {
  for (const plot of [a, b]) {
    if (!Array.isArray(plot) || plot.length !== 4) {
      throw new Error("a plot is four integers: left, bottom, right, top");
    }
    for (const edge of plot) {
      if (!Number.isInteger(edge)) {
        throw new Error("plot edges must be integers");
      }
    }
    if (plot[0] >= plot[2] || plot[1] >= plot[3]) {
      throw new Error("a plot must have positive width and height");
    }
  }
  const width = Math.min(a[2], b[2]) - Math.max(a[0], b[0]);
  const height = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
  if (width <= 0 || height <= 0) {
    return 0;
  }
  return width * height;
}
