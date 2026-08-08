export function accrueFlatInterest(
  principalCents: number,
  rateBasisPoints: number,
  days: number,
  yearBasis: number,
): number {
  const whole = [principalCents, rateBasisPoints, days, yearBasis];
  for (const value of whole) {
    if (!Number.isInteger(value)) {
      throw new Error("every argument must be a whole number");
    }
  }
  if (principalCents < 0 || rateBasisPoints < 0 || days < 0) {
    throw new Error("principal, rate and day count must not be below zero");
  }
  if (yearBasis !== 360 && yearBasis !== 365) {
    throw new Error("the year basis must be 360 or 365");
  }
  const product = principalCents * rateBasisPoints * days;
  const divisor = 10000 * yearBasis;
  return Math.floor((2 * product + divisor) / (2 * divisor));
}
