export function rawTally(
  recipes: Record<string, string[]>,
  item: string,
  batches: number,
): Record<string, number> {
  if (typeof item !== "string" || item.length === 0) {
    throw new Error("item must be a non-empty string");
  }
  if (!Number.isInteger(batches) || batches < 1) {
    throw new Error("batches must be a positive integer");
  }
  const memo = new Map<string, Record<string, number>>();
  const visiting = new Set<string>();
  function expand(name: string): Record<string, number> {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("component names must be non-empty strings");
    }
    const held = memo.get(name);
    if (held !== undefined) {
      return held;
    }
    if (visiting.has(name)) {
      throw new Error("recipe cycle at " + name);
    }
    if (!Object.prototype.hasOwnProperty.call(recipes, name)) {
      return { [name]: 1 };
    }
    const parts = recipes[name];
    if (!Array.isArray(parts) || parts.length === 0) {
      throw new Error("a recipe must list at least one component");
    }
    visiting.add(name);
    const tally: Record<string, number> = {};
    for (const part of parts) {
      const sub = expand(part);
      for (const raw of Object.keys(sub)) {
        tally[raw] = (tally[raw] ?? 0) + sub[raw];
      }
    }
    visiting.delete(name);
    memo.set(name, tally);
    return tally;
  }
  const scaled: Record<string, number> = {};
  for (const [raw, units] of Object.entries(expand(item))) {
    scaled[raw] = units * batches;
  }
  return scaled;
}
