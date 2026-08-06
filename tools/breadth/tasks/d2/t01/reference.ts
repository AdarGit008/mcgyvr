/** Merge overlapping or touching intervals without mutating the input. */
export function mergeIntervals(intervals: [number, number][]): [number, number][] {
  if (!Array.isArray(intervals)) {
    throw new Error("intervals must be an array of [start, end] pairs");
  }
  for (const pair of intervals) {
    if (
      !Array.isArray(pair) ||
      pair.length !== 2 ||
      !Number.isFinite(pair[0]) ||
      !Number.isFinite(pair[1]) ||
      pair[0] > pair[1]
    ) {
      throw new Error("each interval must be [start, end] with finite start <= end");
    }
  }
  const sorted: [number, number][] = intervals
    .map((pair): [number, number] => [pair[0], pair[1]])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged: [number, number][] = [];
  for (const [start, end] of sorted) {
    const last = merged[merged.length - 1];
    if (last !== undefined && start <= last[1]) {
      if (end > last[1]) {
        last[1] = end;
      }
    } else {
      merged.push([start, end]);
    }
  }
  return merged;
}
