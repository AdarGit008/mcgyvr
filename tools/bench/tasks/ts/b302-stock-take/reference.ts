/** The price of one unit, in whole pence. */
export function unitPrice(total: number, count: number): number {
  if (count === 0) {
    throw new Error("count cannot be zero");
  }
  return Math.floor(total / count);
}
