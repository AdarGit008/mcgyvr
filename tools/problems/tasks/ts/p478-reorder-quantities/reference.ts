function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function reorderQuantities(
  lines: Record<string, unknown>[],
): { sku: string; units: number }[] {
  if (!Array.isArray(lines)) {
    throw new Error("reorderQuantities expects a list of lines");
  }

  const buys: { sku: string; units: number }[] = [];
  const seen = new Set<string>();
  for (const line of lines) {
    if (typeof line !== "object" || line === null || Array.isArray(line)) {
      throw new Error("a line is not a mapping");
    }
    if (Object.keys(line).sort().join(",") !== "due,high,low,pack,shelf,sku") {
      throw new Error("a line's keys are not exactly the six named");
    }
    const sku = line["sku"];
    if (typeof sku !== "string" || sku.length === 0) {
      throw new Error("an sku is not a non-empty string");
    }
    if (seen.has(sku)) {
      throw new Error("an sku is repeated");
    }
    seen.add(sku);
    const counts: Record<string, number> = {};
    for (const field of ["shelf", "due", "low"]) {
      const value = line[field];
      if (!whole(value) || (value as number) < 0) {
        throw new Error("a shelf, due or low is not whole or falls below nought");
      }
      counts[field] = value as number;
    }
    const high = line["high"];
    if (!whole(high) || (high as number) < counts["low"]) {
      throw new Error("a high is not whole or falls below the low");
    }
    const pack = line["pack"];
    if (!whole(pack) || (pack as number) < 1) {
      throw new Error("a pack is not whole or falls below one");
    }

    const cover = counts["shelf"] + counts["due"];
    if (cover > counts["low"]) {
      continue;
    }
    const want = (high as number) - cover;
    if (want <= 0) {
      continue;
    }
    const packs = Math.floor((want + (pack as number) - 1) / (pack as number));
    buys.push({ sku, units: packs * (pack as number) });
  }

  return buys;
}
