type Row = { sku: string; aisle: number; bay: number; at: number };

function whole(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

export function serpentinePickOrder(picks: unknown): string[] {
  if (!Array.isArray(picks)) {
    throw new Error("the pick list must be a list");
  }
  const seen = new Set<string>();
  const rows: Row[] = [];
  picks.forEach((pick: unknown, at: number) => {
    if (pick === null || typeof pick !== "object" || Array.isArray(pick)) {
      throw new Error("a pick must be a mapping");
    }
    const record = pick as Record<string, unknown>;
    const sku = record.sku;
    if (typeof sku !== "string" || sku.length === 0) {
      throw new Error("a sku must be a non-empty string");
    }
    if (seen.has(sku)) {
      throw new Error("two picks share a sku");
    }
    seen.add(sku);
    const aisle = record.aisle;
    const bay = record.bay;
    if (!whole(aisle) || aisle < 1) {
      throw new Error("an aisle must be a positive whole number");
    }
    if (!whole(bay) || bay < 1) {
      throw new Error("a bay must be a positive whole number");
    }
    rows.push({ sku, aisle, bay, at });
  });
  rows.sort((left, right) => {
    if (left.aisle !== right.aisle) {
      return left.aisle - right.aisle;
    }
    if (left.bay !== right.bay) {
      return left.aisle % 2 === 1 ? left.bay - right.bay : right.bay - left.bay;
    }
    return left.at - right.at;
  });
  return rows.map((row) => row.sku);
}
