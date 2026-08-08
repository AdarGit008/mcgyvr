const MM: Record<string, number> = { mm: 1, cm: 10, m: 1000, km: 1000000 };

export function convertLength(quantity: string, goal: string): number {
  if (typeof quantity !== "string" || typeof goal !== "string") {
    throw new Error("expected strings");
  }
  if (!(goal in MM)) {
    throw new Error("unknown target symbol");
  }
  if (quantity === "") {
    throw new Error("empty quantity");
  }
  let totalMm = 0;
  for (const part of quantity.split(" ")) {
    const match = /^(\d+)(mm|cm|m|km)$/.exec(part);
    if (match === null) {
      throw new Error("malformed part");
    }
    totalMm += Number(match[1]) * MM[match[2]];
  }
  if (totalMm % MM[goal] !== 0) {
    throw new Error("does not divide evenly into the target");
  }
  return totalMm / MM[goal];
}
