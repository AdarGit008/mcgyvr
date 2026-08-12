function lowestTerms(top: number, bottom: number): [number, number] {
  let a = Math.abs(top);
  let b = bottom;
  while (b !== 0) {
    [a, b] = [b, a % b];
  }
  return [top / a, bottom / a];
}

export function combineMeasures(
  pours: [string, number, number][],
  factor: number[],
): [string, number, number][] {
  if (!Array.isArray(pours)) {
    throw new Error("pours must be a list");
  }
  if (!Array.isArray(factor) || factor.length !== 2) {
    throw new Error("the factor is [numerator, denominator]");
  }
  for (const part of factor) {
    if (!Number.isInteger(part) || part <= 0) {
      throw new Error("factor parts must be positive integers");
    }
  }
  const totals = new Map<string, [number, number]>();
  for (const entry of pours) {
    if (!Array.isArray(entry) || entry.length !== 3) {
      throw new Error("an entry is [name, numerator, denominator]");
    }
    const [name, num, den] = entry;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("names must be non-empty strings");
    }
    if (!Number.isInteger(num) || !Number.isInteger(den)) {
      throw new Error("quantities must be integer fractions");
    }
    if (den <= 0) {
      throw new Error("quantity denominators must be positive");
    }
    const [heldNum, heldDen] = totals.get(name) ?? [0, 1];
    totals.set(name, lowestTerms(heldNum * den + num * heldDen, heldDen * den));
  }
  const mixed: [string, number, number][] = [];
  for (const name of [...totals.keys()].sort()) {
    const [num, den] = totals.get(name) ?? [0, 1];
    const [top, bottom] = lowestTerms(num * factor[0], den * factor[1]);
    mixed.push([name, top, bottom]);
  }
  return mixed;
}
