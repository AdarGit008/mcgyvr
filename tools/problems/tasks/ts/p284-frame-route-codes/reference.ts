type Bin = { name: string; depot: string; low: number; high: number };

const CODE = /^[A-Z]{3}-[0-9]{3}$/;
const DEPOT = /^[A-Z]{3}$/;

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function sortPostalItems(codes: string[], bins: Bin[]): string[] {
  if (!Array.isArray(bins) || bins.length === 0) {
    throw new Error("bins must be a non-empty list");
  }
  const seen = new Set<string>();
  for (const bin of bins) {
    if (bin === null || typeof bin !== "object") {
      throw new Error("a bin must be a record");
    }
    if (typeof bin.name !== "string" || bin.name.length === 0) {
      throw new Error("a bin name must be a non-empty string");
    }
    if (bin.name === "HOLD" || bin.name === "BAD") {
      throw new Error("a bin may not take a mark for a name: " + bin.name);
    }
    if (seen.has(bin.name)) {
      throw new Error("bin names repeat: " + bin.name);
    }
    seen.add(bin.name);
    if (typeof bin.depot !== "string" || !DEPOT.test(bin.depot)) {
      throw new Error("a bin depot must be three capital letters");
    }
    if (!whole(bin.low) || bin.low < 0 || bin.low > 999) {
      throw new Error("low must be an integer from 0 to 999");
    }
    if (!whole(bin.high) || bin.high < 0 || bin.high > 999) {
      throw new Error("high must be an integer from 0 to 999");
    }
    if (bin.low > bin.high) {
      throw new Error("low is above high in bin " + bin.name);
    }
  }
  if (!Array.isArray(codes)) {
    throw new Error("codes must be a list of strings");
  }
  for (const code of codes) {
    if (typeof code !== "string") {
      throw new Error("codes must be a list of strings");
    }
  }

  const routed: string[] = [];
  for (const code of codes) {
    if (!CODE.test(code)) {
      routed.push("BAD");
      continue;
    }
    const depot = code.slice(0, 3);
    const walk = Number(code.slice(4));
    let landed = "HOLD";
    for (const bin of bins) {
      if (bin.depot === depot && walk >= bin.low && walk <= bin.high) {
        landed = bin.name;
        break;
      }
    }
    routed.push(landed);
  }
  return routed;
}
