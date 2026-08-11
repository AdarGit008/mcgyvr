/** Battery gauge readings for a millivolt-calibrated pack. */

export function chargePercent(mv: number, emptyMv: number, fullMv: number): number {
  for (const value of [mv, emptyMv, fullMv]) {
    if (!Number.isInteger(value)) {
      throw new Error("millivolt values must be integers");
    }
  }
  if (emptyMv >= fullMv) {
    throw new Error("empty bound must lie below full bound");
  }
  if (mv <= emptyMv) {
    return 0;
  }
  if (mv >= fullMv) {
    return 100;
  }
  const span = fullMv - emptyMv;
  return Math.floor(((mv - emptyMv) * 200 + span) / (2 * span));
}

export function bandLabel(percent: number): string {
  if (!Number.isInteger(percent) || percent < 0 || percent > 100) {
    throw new Error("percent must be an integer from 0 to 100");
  }
  if (percent < 15) {
    return "low";
  }
  return percent < 85 ? "ok" : "full";
}
