export function tokenBucket(
  capacity: number,
  refill: number,
  requests: number[][],
): string[] {
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  if (!Number.isInteger(refill) || refill < 0) {
    throw new Error("refill must be a non-negative integer");
  }
  const labels: string[] = [];
  let tokens = capacity;
  let previous = 0;
  for (const [time, cost] of requests) {
    if (!Number.isInteger(time) || time < 0) {
      throw new Error("arrival time must be a non-negative integer");
    }
    if (time < previous) {
      throw new Error("arrival times must never decrease");
    }
    if (!Number.isInteger(cost) || cost < 1) {
      throw new Error("cost must be a positive integer");
    }
    tokens = Math.min(capacity, tokens + (time - previous) * refill);
    previous = time;
    if (tokens >= cost) {
      tokens -= cost;
      labels.push("grant");
    } else {
      labels.push("refuse");
    }
  }
  return labels;
}
