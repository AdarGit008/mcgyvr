export function carveSet(steps: Array<[string, number, number]>): number[][] {
  let held: number[][] = [];
  for (const step of steps) {
    const [verb, lo, hi] = step;
    if (verb !== "add" && verb !== "cut") {
      throw new Error("unknown verb");
    }
    if (!Number.isInteger(lo) || !Number.isInteger(hi)) {
      throw new Error("bounds must be integers");
    }
    if (lo >= hi) {
      throw new Error("lo must be strictly below hi");
    }
    const next: number[][] = [];
    if (verb === "add") {
      let start = lo;
      let stop = hi;
      for (const [a, b] of held) {
        if (b < start || a > stop) {
          next.push([a, b]);
        } else {
          start = Math.min(start, a);
          stop = Math.max(stop, b);
        }
      }
      next.push([start, stop]);
      next.sort((x, y) => x[0] - y[0]);
    } else {
      for (const [a, b] of held) {
        if (b <= lo || a >= hi) {
          next.push([a, b]);
        } else {
          if (a < lo) next.push([a, lo]);
          if (hi < b) next.push([hi, b]);
        }
      }
    }
    held = next;
  }
  return held;
}
