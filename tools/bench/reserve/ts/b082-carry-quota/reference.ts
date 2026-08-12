/** Bill a metered plan's per-period overage under capped carry-over. */
export function billOverage(
  allowance: number,
  carryCap: number,
  usage: number[],
): { billed: number[]; carried: number } {
  if (!Number.isInteger(allowance) || allowance < 0) {
    throw new Error("allowance must be a non-negative integer");
  }
  if (!Number.isInteger(carryCap) || carryCap < 0) {
    throw new Error("carry cap must be a non-negative integer");
  }
  if (!Array.isArray(usage)) {
    throw new Error("usage must be a list");
  }
  const billed: number[] = [];
  let carried = 0;
  for (const used of usage) {
    if (!Number.isInteger(used) || used < 0) {
      throw new Error("each period's usage must be a non-negative integer");
    }
    const available = allowance + carried;
    if (used > available) {
      billed.push(used - available);
      carried = 0;
    } else {
      billed.push(0);
      carried = Math.min(carryCap, available - used);
    }
  }
  return { billed, carried };
}
