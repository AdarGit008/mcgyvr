/** Flatten nested arrays up to depth levels; strings stay whole. */
export function flatten(items: readonly unknown[], depth: number = Infinity): unknown[] {
  if (depth !== Infinity && (!Number.isInteger(depth) || depth < 0)) {
    throw new Error(`depth must be a non-negative integer or Infinity, got ${depth}`);
  }
  const out: unknown[] = [];
  for (const item of items) {
    if (Array.isArray(item) && depth > 0) {
      out.push(...flatten(item, depth === Infinity ? Infinity : depth - 1));
    } else {
      out.push(item);
    }
  }
  return out;
}
