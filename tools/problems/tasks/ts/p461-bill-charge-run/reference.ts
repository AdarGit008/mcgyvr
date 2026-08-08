function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function billChargeRun(
  prices: any[],
  draw: number,
  target: number,
): { slots: number[]; units: number; bill: number; short: number } {
  if (!Array.isArray(prices)) {
    throw new Error("prices must be a list");
  }
  for (const price of prices) {
    if (!whole(price) || price < 0) {
      throw new Error("every price must be a whole number of nought or more");
    }
  }
  if (!whole(draw) || draw < 1) {
    throw new Error("draw must be a whole number above nought");
  }
  if (!whole(target) || target < 0) {
    throw new Error("target must be a whole number of nought or more");
  }

  const order = prices.map((_price, index) => index);
  order.sort((a, b) => (prices[a] !== prices[b] ? prices[a] - prices[b] : a - b));

  const taken = new Map<number, number>();
  let owed = target;
  let bill = 0;
  for (const slot of order) {
    if (owed === 0) break;
    const units = draw < owed ? draw : owed;
    taken.set(slot, units);
    bill += units * prices[slot];
    owed -= units;
  }

  const slots = [...taken.keys()].sort((a, b) => a - b);
  return { slots, units: target - owed, bill, short: owed };
}
