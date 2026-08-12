/**
 * A deterministic irrigation reservoir. Each tick adds its inflow (water
 * above the capacity spills), then draws its demand (whatever the level
 * cannot cover counts as shortfall; what it can cover counts as served).
 */
export function runReservoir(
  capacity: number,
  start: number,
  ticks: number[][],
): { level: number; spilled: number; shortfall: number; served: number } {
  if (!Number.isInteger(capacity) || capacity <= 0) {
    throw new Error("capacity must be a positive integer");
  }
  if (!Number.isInteger(start)) {
    throw new Error("start level must be an integer");
  }
  if (start < 0 || start > capacity) {
    throw new Error("start level must lie within the capacity");
  }
  let level = start;
  let spilled = 0;
  let shortfall = 0;
  let served = 0;
  for (const tick of ticks) {
    if (!Array.isArray(tick) || tick.length !== 2) {
      throw new Error("each tick is an [inflow, demand] pair");
    }
    const [inflow, demand] = tick;
    if (!Number.isInteger(inflow) || inflow < 0) {
      throw new Error("inflow must be a non-negative integer");
    }
    if (!Number.isInteger(demand) || demand < 0) {
      throw new Error("demand must be a non-negative integer");
    }
    level += inflow;
    if (level > capacity) {
      spilled += level - capacity;
      level = capacity;
    }
    const drawn = Math.min(level, demand);
    served += drawn;
    shortfall += demand - drawn;
    level -= drawn;
  }
  return { level, spilled, shortfall, served };
}
