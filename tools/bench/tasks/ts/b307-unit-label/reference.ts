export function shortUnit(unit: string): string {
  return unit.slice(0, 3);
}

/** An amount written with its unit. */
export function labelOf(amount: number, unit: string): string {
  if (amount < 0) {
    throw new Error("amount cannot be negative");
  }
  if (amount === 1) {
    return String(amount) + " " + unit;
  }
  return String(amount) + " " + unit + "s";
}
