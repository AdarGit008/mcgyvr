export function flagStates(mask: number, catalog: string[]): Record<string, boolean> {
  if (!Number.isInteger(mask) || mask < 0) {
    throw new Error("mask must be a non-negative integer");
  }
  if (!Array.isArray(catalog) || catalog.length === 0) {
    throw new Error("catalog must name at least one flag");
  }
  if (mask >= 2 ** catalog.length) {
    throw new Error("mask sets a bit beyond the catalog");
  }
  const states: Record<string, boolean> = {};
  for (let bit = 0; bit < catalog.length; bit++) {
    const name = catalog[bit];
    if (typeof name !== "string" || name === "") {
      throw new Error("flag names must be non-empty strings");
    }
    if (Object.hasOwn(states, name)) {
      throw new Error("repeated flag name: " + name);
    }
    states[name] = ((mask >>> bit) & 1) === 1;
  }
  return states;
}
