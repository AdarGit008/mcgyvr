/** Skyline by coordinate compression: max height over each critical segment. */
export function skyline(
  buildings: [number, number, number][],
): [number, number][] {
  const xsSet: Set<number> = new Set();
  for (const [left, right] of buildings) {
    xsSet.add(left);
    xsSet.add(right);
  }
  const xs = [...xsSet].sort((a, b) => a - b);
  const out: [number, number][] = [];
  let prevHeight = 0;
  for (let k = 0; k < xs.length; k++) {
    const x = xs[k];
    let height = 0;
    if (k < xs.length - 1) {
      const next = xs[k + 1];
      // A building covers the whole segment [x, next) exactly when it spans
      // both endpoints; segments never straddle a building edge.
      for (const [left, right, h] of buildings) {
        if (left <= x && right >= next && h > height) height = h;
      }
    }
    if (height !== prevHeight) {
      out.push([x, height]);
      prevHeight = height;
    }
  }
  return out;
}
