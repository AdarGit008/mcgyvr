export function tierRate(units: number): number {
  if (units < 10) {
    return 50;
  }
  if (units < 50) {
    return 40;
  }
  return 30;
}

/** The whole charge in cents for a count of units. */
export function tierCost(units: number): number {
  if (units === 0) {
    return 0;
  }
  const gross = units * tierRate(units);
  if (gross < 100) {
    return 100;
  }
  return gross;
}
