export function stampTable(dies: [string, number][]): Map<string, number> {
  const table = new Map<string, number>();
  for (const [fragment, price] of dies) {
    if (typeof fragment !== "string" || fragment.length === 0) {
      throw new Error("a die fragment must be a non-empty string");
    }
    if (!Number.isInteger(price) || price <= 0) {
      throw new Error("a die price must be a positive integer");
    }
    if (table.has(fragment)) {
      throw new Error("die listed twice: " + fragment);
    }
    table.set(fragment, price);
  }
  return table;
}

export function stampCover(label: string, dies: [string, number][]): number {
  if (typeof label !== "string" || label.length === 0) {
    throw new Error("the label must be a non-empty string");
  }
  const table = stampTable(dies);
  const best: number[] = new Array(label.length + 1).fill(Infinity);
  best[0] = 0;
  for (let end = 1; end <= label.length; end++) {
    for (const [fragment, price] of table) {
      const start = end - fragment.length;
      if (start < 0 || best[start] + price >= best[end]) {
        continue;
      }
      if (label.slice(start, end) === fragment) {
        best[end] = best[start] + price;
      }
    }
  }
  if (!Number.isFinite(best[label.length])) {
    throw new Error("no sequence of dies spells the label");
  }
  return best[label.length];
}
