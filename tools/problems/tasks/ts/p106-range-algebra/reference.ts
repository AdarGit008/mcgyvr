function validated(intervals: number[][]): number[][] {
  for (const entry of intervals) {
    if (
      !Array.isArray(entry) ||
      entry.length !== 2 ||
      !Number.isInteger(entry[0]) ||
      !Number.isInteger(entry[1])
    ) {
      throw new Error("an interval must be a pair of integers");
    }
    if (entry[0] >= entry[1]) {
      throw new Error("lo must be strictly below hi");
    }
  }
  return intervals;
}

function canonical(intervals: number[][]): number[][] {
  const sorted = intervals
    .map((pair) => [pair[0], pair[1]])
    .sort((x, y) => x[0] - y[0]);
  const out: number[][] = [];
  for (const [lo, hi] of sorted) {
    const last = out[out.length - 1];
    if (last !== undefined && lo <= last[1]) {
      last[1] = Math.max(last[1], hi);
    } else {
      out.push([lo, hi]);
    }
  }
  return out;
}

export function rangeAlgebra(a: number[][], b: number[][], op: string): number[][] {
  if (op !== "union" && op !== "intersect" && op !== "subtract") {
    throw new Error("unknown op");
  }
  const left = canonical(validated(a));
  const right = canonical(validated(b));
  if (op === "union") {
    return canonical([...left, ...right]);
  }
  const out: number[][] = [];
  if (op === "intersect") {
    for (const [lo, hi] of left) {
      for (const [s, e] of right) {
        const from = Math.max(lo, s);
        const to = Math.min(hi, e);
        if (from < to) out.push([from, to]);
      }
    }
    return canonical(out);
  }
  for (const piece of left) {
    let [lo, hi] = piece;
    let dead = false;
    for (const [s, e] of right) {
      if (e <= lo || s >= hi) continue;
      if (s > lo) out.push([lo, s]);
      lo = Math.max(lo, e);
      if (lo >= hi) {
        dead = true;
        break;
      }
    }
    if (!dead) out.push([lo, hi]);
  }
  return canonical(out);
}
