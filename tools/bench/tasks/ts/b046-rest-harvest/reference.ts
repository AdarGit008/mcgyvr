/** The most kilos a picker can take when a worked day forces a rest day. */

export function bestHarvest(yields: number[]): number {
  if (!Array.isArray(yields)) {
    throw new Error("bestHarvest expects a list of daily yields");
  }
  // Best totals so far, split by whether the previous day was worked.
  let rested = 0;
  let picked = 0;
  for (const kilos of yields) {
    if (!Number.isInteger(kilos) || kilos < 0) {
      throw new Error("every daily yield must be a non-negative integer");
    }
    // Working today is only lawful on top of a rested yesterday.
    const workToday = rested + kilos;
    rested = Math.max(rested, picked);
    picked = workToday;
  }
  return Math.max(rested, picked);
}
