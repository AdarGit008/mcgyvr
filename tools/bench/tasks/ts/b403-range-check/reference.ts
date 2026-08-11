export function rangeCheck(
  readings: number[],
  low: number,
  high: number,
): boolean {
  if (low > high) {
    throw new Error("the low must not stand above the high");
  }
  for (const reading of readings) {
    if (reading < low || reading > high) {
      return false;
    }
  }
  return true;
}
