/** The free stretches of a working window, given its busy intervals. */
export function freeWindows(
  windowStart: number,
  windowEnd: number,
  busy: number[][],
): number[][] {
  if (!Number.isInteger(windowStart) || !Number.isInteger(windowEnd)) {
    throw new Error("window bounds must be integers");
  }
  if (windowStart >= windowEnd) {
    throw new Error("window start must precede its end");
  }
  const clipped: number[][] = [];
  for (const interval of busy) {
    const [start, end] = interval;
    if (!Number.isInteger(start) || !Number.isInteger(end)) {
      throw new Error("busy endpoints must be integers");
    }
    if (start >= end) {
      throw new Error("busy start must precede its end");
    }
    const s = Math.max(start, windowStart);
    const e = Math.min(end, windowEnd);
    if (s < e) {
      clipped.push([s, e]);
    }
  }
  clipped.sort((a, b) => a[0] - b[0]);
  const gaps: number[][] = [];
  let cursor = windowStart;
  for (const [start, end] of clipped) {
    if (start > cursor) {
      gaps.push([cursor, start]);
    }
    if (end > cursor) {
      cursor = end;
    }
  }
  if (cursor < windowEnd) {
    gaps.push([cursor, windowEnd]);
  }
  return gaps;
}
