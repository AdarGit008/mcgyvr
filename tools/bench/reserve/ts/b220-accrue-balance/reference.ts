/** Grow a whole-cent balance, carrying the sub-cent interest between periods. */
export function accrueBalance(opening: number, rate: number, periods: number): number {
  if (!Number.isInteger(rate) || rate < 0) {
    throw new Error("rate must be a whole number of basis points of at least 0");
  }
  if (!Number.isInteger(periods) || periods < 0) {
    throw new Error("periods must be a whole number of at least 0");
  }
  const scale = 10000;
  let total = opening;
  let carry = 0;
  for (let step = 0; step < periods; step++) {
    carry += total * rate;
    const cents = Math.floor(carry / scale);
    total += cents;
    carry -= cents * scale;
  }
  if (carry * 2 > scale || (carry * 2 === scale && total % 2 === 1)) {
    total += 1;
  }
  return total;
}
