export function baseAmount(amount: number, unit: string, defs: Record<string, [number, string]>, base: string): number {
  if (!Number.isInteger(amount) || amount < 0) {
    throw new Error("amount must be a non-negative integer");
  }
  const unwind = (count: number, name: string, depth: number): number => {
    if (name === base) {
      return count;
    }
    if (depth > Object.keys(defs).length || !(name in defs)) {
      throw new Error("unit is unknown or its chain never reaches the base");
    }
    const [factor, finer] = defs[name];
    if (!Number.isInteger(factor) || factor < 1) {
      throw new Error("factor must be a positive integer");
    }
    return unwind(count * factor, finer, depth + 1);
  };
  return unwind(amount, unit, 0);
}
