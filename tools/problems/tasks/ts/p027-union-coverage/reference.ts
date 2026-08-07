export function unionCoverage(rects: number[][]): number {
  if (!Array.isArray(rects)) {
    throw new Error("unionCoverage expects a list of rectangles");
  }
  for (const rect of rects) {
    if (
      !Array.isArray(rect) ||
      rect.length !== 4 ||
      rect.some((c) => !Number.isInteger(c))
    ) {
      throw new Error("each rectangle must be four integers");
    }
    const [x1, y1, x2, y2] = rect;
    if (x1 >= x2 || y1 >= y2) {
      throw new Error("rectangle corners must satisfy x1 < x2 and y1 < y2");
    }
    if (rect.some((c) => c < -10000 || c > 10000)) {
      throw new Error("coordinates must stay within -10000..10000");
    }
  }
  if (rects.length === 0) {
    return 0;
  }
  const xs = [...new Set(rects.flatMap((r) => [r[0], r[2]]))].sort((a, b) => a - b);
  const ys = [...new Set(rects.flatMap((r) => [r[1], r[3]]))].sort((a, b) => a - b);
  let area = 0;
  for (let i = 0; i < xs.length - 1; i++) {
    for (let j = 0; j < ys.length - 1; j++) {
      const covered = rects.some(
        (r) => r[0] <= xs[i] && xs[i + 1] <= r[2] && r[1] <= ys[j] && ys[j + 1] <= r[3],
      );
      if (covered) {
        area += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j]);
      }
    }
  }
  return area;
}
