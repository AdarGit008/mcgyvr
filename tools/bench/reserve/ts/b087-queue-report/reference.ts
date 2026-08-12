export function queueReport(orders: number[][]): Record<string, number> {
  if (!Array.isArray(orders)) {
    throw new Error("queueReport expects a list of orders");
  }
  let finish = 0;
  let waited = 0;
  let longest = 0;
  let busy = 0;
  let previous = 0;
  for (const entry of orders) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("each order is a pair");
    }
    const [placed, handover] = entry;
    if (!Number.isInteger(placed) || placed < 0) {
      throw new Error("placement minute must be a non-negative integer");
    }
    if (!Number.isInteger(handover) || handover < 1) {
      throw new Error("hand-over time must be a positive integer");
    }
    if (placed < previous) {
      throw new Error("placement minutes must never decrease");
    }
    previous = placed;
    const start = Math.max(placed, finish);
    const wait = start - placed;
    waited += wait;
    longest = Math.max(longest, wait);
    finish = start + handover;
    busy += handover;
  }
  return { waited, longest, idle: finish - busy };
}
