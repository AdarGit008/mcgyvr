/** Fill a produce order from storage lots, freshest expiry first. */
export function pickHarvestLots(
  lots: [string, number, number, number][],
  needed: number,
  cap: number,
  today: number,
): {
  picks: [string, number][];
  cost: number;
  shortfall: number;
  skipped: string[];
  leftovers: [string, number][];
} {
  if (!Number.isInteger(needed) || needed <= 0) {
    throw new Error("order quantity must be a positive integer");
  }
  if (!Number.isInteger(cap) || cap <= 0) {
    throw new Error("per-lot cap must be a positive integer");
  }
  if (!Number.isInteger(today)) {
    throw new Error("current day must be an integer");
  }
  const seen = new Set<string>();
  const usable: [string, number, number, number][] = [];
  const skipped: string[] = [];
  for (const lot of lots) {
    if (!Array.isArray(lot) || lot.length !== 4) {
      throw new Error("a lot must be a [name, expiry, cost, quantity] quadruple");
    }
    const [name, expiry, unitCost, quantity] = lot;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("lot name must be a non-empty string");
    }
    if (seen.has(name)) {
      throw new Error("repeated lot name: " + name);
    }
    seen.add(name);
    if (!Number.isInteger(expiry)) {
      throw new Error("expiry day must be an integer");
    }
    if (!Number.isInteger(unitCost) || unitCost < 0) {
      throw new Error("unit cost must be a non-negative integer");
    }
    if (!Number.isInteger(quantity) || quantity <= 0) {
      throw new Error("lot quantity must be a positive integer");
    }
    if (expiry > today) {
      usable.push([name, expiry, unitCost, quantity]);
    } else {
      skipped.push(name);
    }
  }
  usable.sort((a, b) => {
    if (a[1] !== b[1]) {
      return a[1] - b[1];
    }
    if (a[2] !== b[2]) {
      return a[2] - b[2];
    }
    return a[0] < b[0] ? -1 : 1;
  });
  const picks: [string, number][] = [];
  const leftovers: [string, number][] = [];
  let cost = 0;
  let remaining = needed;
  for (const [name, , unitCost, quantity] of usable) {
    let taken = quantity < cap ? quantity : cap;
    if (taken > remaining) {
      taken = remaining;
    }
    if (taken > 0) {
      picks.push([name, taken]);
      cost += taken * unitCost;
      remaining -= taken;
    }
    if (quantity - taken > 0) {
      leftovers.push([name, quantity - taken]);
    }
  }
  return { picks, cost, shortfall: remaining, skipped, leftovers };
}
