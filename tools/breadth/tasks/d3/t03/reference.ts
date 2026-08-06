/** Weighted interval scheduling: sort by end, DP over prefixes, walk back. */
type Interval = { start: number; end: number; weight: number };

export function schedule(
  intervals: Interval[],
): { total: number; chosen: number[] } {
  const order = intervals.map((_, i) => i);
  order.sort(
    (a, b) =>
      intervals[a].end - intervals[b].end ||
      intervals[a].start - intervals[b].start,
  );
  const n = order.length;
  const prev: number[] = [];
  for (let k = 0; k < n; k++) {
    const s = intervals[order[k]].start;
    let lo = 0;
    let hi = k - 1;
    let best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (intervals[order[mid]].end <= s) {
        best = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    prev.push(best);
  }
  const dp: number[] = [0];
  for (let k = 1; k <= n; k++) {
    const take = intervals[order[k - 1]].weight + dp[prev[k - 1] + 1];
    dp.push(Math.max(dp[k - 1], take));
  }
  const chosen: number[] = [];
  let k = n;
  while (k > 0) {
    if (dp[k] === dp[k - 1]) {
      k -= 1;
    } else {
      chosen.push(order[k - 1]);
      k = prev[k - 1] + 1;
    }
  }
  chosen.sort((a, b) => a - b);
  return { total: dp[n], chosen };
}
