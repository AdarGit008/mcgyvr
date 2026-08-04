/** Merge overlapping or touching [start, end] pairs without mutating the input. */
export function mergeIntervals(intervals: number[][]): number[][] {
  for (const pair of intervals) {
    if (pair[0] > pair[1]) {
      throw new Error(`interval start must not exceed end, got [${pair[0]}, ${pair[1]}]`);
    }
  }
  const sorted = intervals.map((pair) => [pair[0], pair[1]]).sort((a, b) => a[0] - b[0]);
  const merged: number[][] = [];
  for (const [start, end] of sorted) {
    const last = merged[merged.length - 1];
    if (last !== undefined && start <= last[1]) {
      last[1] = Math.max(last[1], end);
    } else {
      merged.push([start, end]);
    }
  }
  return merged;
}
