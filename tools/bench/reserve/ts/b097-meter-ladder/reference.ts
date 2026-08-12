export function meterCharge(units: number, tiers: number[][]): number {
  if (!Number.isInteger(units)) {
    throw new Error("units must be an integer");
  }
  if (units < 0) {
    throw new Error("units must not be negative");
  }
  if (!Array.isArray(tiers) || tiers.length === 0) {
    throw new Error("the ladder needs at least one tier");
  }
  let capacity = 0;
  for (const [span, rate] of tiers) {
    if (!Number.isInteger(span) || span <= 0) {
      throw new Error("a tier span must be a positive integer");
    }
    if (!Number.isInteger(rate) || rate < 0) {
      throw new Error("a tier rate must be a non-negative integer");
    }
    capacity += span;
  }
  if (units > capacity) {
    throw new Error("consumption exceeds the ladder");
  }
  let remaining = units;
  let cents = 0;
  for (const [span, rate] of tiers) {
    const used = Math.min(remaining, span);
    remaining -= used;
    cents += Math.floor((used * rate + 500) / 1000);
  }
  return cents;
}
