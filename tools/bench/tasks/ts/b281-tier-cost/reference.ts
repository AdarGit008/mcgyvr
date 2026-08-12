export function tierCost(
  units: number,
  allowance: number,
  firstRate: number,
  laterRate: number,
): number {
  if (units < 0) {
    throw new Error("units cannot be negative");
  }
  if (units <= allowance) {
    return units * firstRate;
  }
  return allowance * firstRate + (units - allowance) * laterRate;
}
