/** Stock lookup across a storeroom's nested zones. */

export function rackUnits(bins: Record<string, number>, sku: string): number {
  if (typeof sku !== "string" || sku === "") {
    throw new Error("sku must be a non-empty string");
  }
  if (!(sku in bins)) {
    return 0;
  }
  const qty = bins[sku];
  if (!Number.isInteger(qty) || qty <= 0) {
    throw new Error("a recorded count must be a positive integer");
  }
  return qty;
}

export function zoneStock(
  zone: Record<string, unknown>,
  sku: string,
): { total: number; holders: string[] } {
  const seen = new Set<string>();
  const holders: string[] = [];
  function walk(node: unknown): number {
    if (typeof node !== "object" || node === null || Array.isArray(node)) {
      throw new Error("a zone must be a record");
    }
    const { name, bins, children } = node as Record<string, unknown>;
    if (typeof name !== "string" || name === "") {
      throw new Error("a zone name must be a non-empty string");
    }
    if (seen.has(name)) {
      throw new Error("zone names must be unique across the storeroom");
    }
    seen.add(name);
    if (typeof bins !== "object" || bins === null || Array.isArray(bins)) {
      throw new Error("bins must be a mapping of sku to units");
    }
    if (!Array.isArray(children)) {
      throw new Error("children must be a list of zones");
    }
    let units = rackUnits(bins as Record<string, number>, sku);
    if (units > 0) {
      holders.push(name);
    }
    for (const child of children) {
      units += walk(child);
    }
    return units;
  }
  return { total: walk(zone), holders };
}
