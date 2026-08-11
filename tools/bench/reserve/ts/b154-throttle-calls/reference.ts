/** Decide each call against a sliding window of the accepted arrivals. */
export function throttleCalls(times: number[], limit: number, window: number): boolean[] {
  if (!Array.isArray(times)) throw new Error("throttleCalls expects a list of arrival times");
  if (!Number.isInteger(limit) || limit < 1) throw new Error("limit must be a positive integer");
  if (!Number.isInteger(window) || window < 1) throw new Error("window must be a positive integer");
  const accepted: number[] = [];
  const verdicts: boolean[] = [];
  let previous = 0;
  for (const now of times) {
    if (!Number.isInteger(now) || now < 0 || now < previous) {
      throw new Error("arrivals must be non-decreasing non-negative integers");
    }
    previous = now;
    while (accepted.length > 0 && now - accepted[0] >= window) accepted.shift();
    verdicts.push(accepted.length < limit);
    if (accepted.length < limit) accepted.push(now);
  }
  return verdicts;
}
