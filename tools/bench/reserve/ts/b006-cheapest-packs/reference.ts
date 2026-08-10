/** Cheapest exact fulfilment of an order from priced packs. */

export function cheapestPacks(order: number, packs: number[][]): number {
  if (!Number.isInteger(order) || order < 0) {
    throw new Error("order must be a non-negative integer");
  }
  if (!Array.isArray(packs) || packs.length === 0) {
    throw new Error("at least one pack is required");
  }
  for (const [size, price] of packs) {
    if (!Number.isInteger(size) || size <= 0) {
      throw new Error("pack size must be a positive integer");
    }
    if (!Number.isInteger(price) || price < 0) {
      throw new Error("pack price must be a non-negative integer");
    }
  }
  const best: (number | null)[] = new Array(order + 1).fill(null);
  best[0] = 0;
  for (let units = 1; units <= order; units++) {
    for (const [size, price] of packs) {
      if (size > units || best[units - size] === null) {
        continue;
      }
      const cost = (best[units - size] as number) + price;
      const current = best[units];
      if (current === null || cost < current) {
        best[units] = cost;
      }
    }
  }
  return best[order] === null ? -1 : (best[order] as number);
}
