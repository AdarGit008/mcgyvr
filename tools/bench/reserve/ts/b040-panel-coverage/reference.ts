/** Coverage statistics for axis-aligned panels laid over an integer grid. */
export function panelCoverage(panels: number[][]): {
  union: number;
  overlap: number;
  deepest: number;
  perimeter: number;
  bounds: number[] | null;
} {
  if (!Array.isArray(panels)) {
    throw new Error("panels must be a list");
  }
  for (const panel of panels) {
    if (!Array.isArray(panel) || panel.length !== 4) {
      throw new Error("each panel is an [x1, y1, x2, y2] list");
    }
    for (const edge of panel) {
      if (!Number.isInteger(edge)) {
        throw new Error("panel coordinates must be integers");
      }
    }
    if (panel[0] >= panel[2] || panel[1] >= panel[3]) {
      throw new Error("panel edges must be in increasing order");
    }
  }
  if (panels.length === 0) {
    return { union: 0, overlap: 0, deepest: 0, perimeter: 0, bounds: null };
  }
  // Compress the plane at every panel edge; inside one compressed cell
  // the stack of panels over any point is constant.
  const xs = [...new Set(panels.flatMap((p) => [p[0], p[2]]))].sort(
    (a, b) => a - b,
  );
  const ys = [...new Set(panels.flatMap((p) => [p[1], p[3]]))].sort(
    (a, b) => a - b,
  );
  const covered: boolean[][] = xs.map(() => ys.map(() => false));
  let union = 0;
  let overlap = 0;
  let deepest = 0;
  for (let i = 0; i + 1 < xs.length; i++) {
    for (let j = 0; j + 1 < ys.length; j++) {
      let depth = 0;
      for (const p of panels) {
        if (
          p[0] <= xs[i] &&
          xs[i + 1] <= p[2] &&
          p[1] <= ys[j] &&
          ys[j + 1] <= p[3]
        ) {
          depth += 1;
        }
      }
      const area = (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j]);
      if (depth >= 1) {
        union += area;
        covered[i][j] = true;
      }
      if (depth >= 2) {
        overlap += area;
      }
      if (depth > deepest) {
        deepest = depth;
      }
    }
  }
  // The union's boundary: each covered cell contributes the sides that
  // face uncovered ground or the outside; seams between covered cells
  // are interior and add nothing.
  let perimeter = 0;
  for (let i = 0; i + 1 < xs.length; i++) {
    for (let j = 0; j + 1 < ys.length; j++) {
      if (!covered[i][j]) {
        continue;
      }
      const width = xs[i + 1] - xs[i];
      const height = ys[j + 1] - ys[j];
      if (i === 0 || !covered[i - 1][j]) {
        perimeter += height;
      }
      if (i + 2 === xs.length || !covered[i + 1][j]) {
        perimeter += height;
      }
      if (j === 0 || !covered[i][j - 1]) {
        perimeter += width;
      }
      if (j + 2 === ys.length || !covered[i][j + 1]) {
        perimeter += width;
      }
    }
  }
  const bounds = [
    Math.min(...panels.map((p) => p[0])),
    Math.min(...panels.map((p) => p[1])),
    Math.max(...panels.map((p) => p[2])),
    Math.max(...panels.map((p) => p[3])),
  ];
  return { union, overlap, deepest, perimeter, bounds };
}
