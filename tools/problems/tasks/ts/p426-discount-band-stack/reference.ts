const RULE_KEYS = ["amount", "band", "code", "floor", "mode", "solo"];

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function subtotalOf(basket: (string | number)[][]): number {
  if (!Array.isArray(basket)) {
    throw new Error("the basket must be a list of triples");
  }
  let subtotal = 0;
  for (const line of basket) {
    if (!Array.isArray(line) || line.length !== 3) {
      throw new Error("a basket line is a [sku, unitCents, count] triple");
    }
    const sku = line[0];
    const unitCents = line[1];
    const count = line[2];
    if (typeof sku !== "string" || sku.length === 0) {
      throw new Error("a sku must be a non-empty string");
    }
    if (!whole(unitCents) || (unitCents as number) < 0) {
      throw new Error("unit cents must be whole and at nought or above");
    }
    if (!whole(count) || (count as number) < 1) {
      throw new Error("a count must be a whole number of at least one");
    }
    subtotal += (unitCents as number) * (count as number);
  }
  return subtotal;
}

export function applyDiscountBands(
  basket: (string | number)[][],
  rules: Record<string, unknown>[],
): { total: number; applied: string[] } {
  let running = subtotalOf(basket);
  if (!Array.isArray(rules)) {
    throw new Error("the rules must be a list of mappings");
  }

  const seen = new Set<string>();
  for (const rule of rules) {
    if (rule === null || typeof rule !== "object" || Array.isArray(rule)) {
      throw new Error("a rule must be a mapping");
    }
    const keys = Object.keys(rule).sort();
    if (keys.length !== RULE_KEYS.length || keys.some((k, i) => k !== RULE_KEYS[i])) {
      throw new Error("a rule carries exactly code, band, mode, amount, floor, solo");
    }
    const code = rule.code;
    if (typeof code !== "string" || code.length === 0) {
      throw new Error("a code must be a non-empty string");
    }
    if (seen.has(code)) {
      throw new Error(`two rules share the code ${code}`);
    }
    seen.add(code);
    if (typeof rule.band !== "string" || rule.band.length === 0) {
      throw new Error("a band must be a non-empty string");
    }
    if (rule.mode !== "share" && rule.mode !== "flat") {
      throw new Error("a mode is either share or flat");
    }
    const amount = rule.amount;
    if (rule.mode === "share") {
      if (!whole(amount) || (amount as number) < 1 || (amount as number) > 100) {
        throw new Error("a share amount runs from 1 through 100");
      }
    } else if (!whole(amount) || (amount as number) < 1) {
      throw new Error("a flat amount must be a whole number of cents above nought");
    }
    if (!whole(rule.floor) || (rule.floor as number) < 0) {
      throw new Error("a floor must be whole and at nought or above");
    }
    if (typeof rule.solo !== "boolean") {
      throw new Error("a solo flag must be a boolean");
    }
  }

  const bitten = new Set<string>();
  const applied: string[] = [];
  for (const rule of rules) {
    const band = rule.band as string;
    if (bitten.has(band)) {
      continue;
    }
    if (running < (rule.floor as number)) {
      continue;
    }
    const amount = rule.amount as number;
    const cut =
      rule.mode === "share"
        ? Math.floor((running * amount) / 100)
        : Math.min(amount, running);
    running -= cut;
    bitten.add(band);
    applied.push(rule.code as string);
    if (rule.solo === true) {
      break;
    }
  }
  return { total: running, applied };
}
