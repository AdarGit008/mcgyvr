function priceOf(row: any): number {
  if (!Number.isInteger(row.price) || row.price < 1) {
    throw new Error("a price must be a whole number of pence, one or more");
  }
  return row.price;
}

function codeOf(row: any): string {
  if (row === null || typeof row !== "object" || Array.isArray(row)) {
    throw new Error("everything on sale must be a record");
  }
  if (typeof row.code !== "string" || row.code === "") {
    throw new Error("a code must be a non-empty string");
  }
  return row.code;
}

function reads(left: string[], right: string[]): number {
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) {
      return left[i] < right[i] ? -1 : 1;
    }
  }
  return left.length - right.length;
}

export function cheapestTray(items: any[], bundles: any[], needed: any[]): any {
  if (!Array.isArray(items) || !Array.isArray(bundles) || !Array.isArray(needed)) {
    throw new Error("items, bundles and the requirement must all be lists");
  }
  if (items.length + bundles.length > 14) {
    throw new Error("more than fourteen things on sale is too many to search");
  }

  const onSale = new Set<string>();
  const sold = new Set<string>();
  const options: any[] = [];
  for (const row of items) {
    const code = codeOf(row);
    if (onSale.has(code)) {
      throw new Error("two things on sale share the code " + code);
    }
    onSale.add(code);
    sold.add(code);
    options.push({ code, price: priceOf(row), holds: [code] });
  }
  for (const row of bundles) {
    const code = codeOf(row);
    if (onSale.has(code)) {
      throw new Error("two things on sale share the code " + code);
    }
    onSale.add(code);
    if (!Array.isArray(row.holds) || row.holds.length === 0) {
      throw new Error("bundle " + code + " holds nothing");
    }
    for (const held of row.holds) {
      if (!sold.has(held)) {
        throw new Error("bundle " + code + " holds an unknown code");
      }
    }
    options.push({ code, price: priceOf(row), holds: row.holds });
  }

  const wanted = new Map<string, number>();
  for (const code of needed) {
    if (!sold.has(code)) {
      throw new Error("no item sells the required code " + String(code));
    }
    if (wanted.has(code)) {
      throw new Error("the code " + code + " is required twice");
    }
    wanted.set(code, wanted.size);
  }

  const masks: number[] = options.map((option) => {
    let mask = 0;
    for (const held of option.holds) {
      const bit = wanted.get(held);
      if (bit !== undefined) {
        mask |= 1 << bit;
      }
    }
    return mask;
  });

  const full = (1 << wanted.size) - 1;
  let bestCost = 0;
  let bestPicks: string[] | null = null;
  for (let subset = 0; subset < 1 << options.length; subset++) {
    let mask = 0;
    let cost = 0;
    const picks: string[] = [];
    for (let i = 0; i < options.length; i++) {
      if (subset & (1 << i)) {
        mask |= masks[i];
        cost += options[i].price;
        picks.push(options[i].code);
      }
    }
    if (mask !== full) {
      continue;
    }
    picks.sort();
    if (
      bestPicks === null ||
      cost < bestCost ||
      (cost === bestCost && picks.length < bestPicks.length) ||
      (cost === bestCost &&
        picks.length === bestPicks.length &&
        reads(picks, bestPicks) < 0)
    ) {
      bestCost = cost;
      bestPicks = picks;
    }
  }

  return { total: bestCost, picks: bestPicks === null ? [] : bestPicks };
}
