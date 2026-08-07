function readUnits(raw: unknown): Map<string, number> {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("units must be a mapping");
  }
  const units = new Map<string, number>();
  for (const [name, exponent] of Object.entries(raw as Record<string, unknown>)) {
    if (!/^[a-z]+$/.test(name)) {
      throw new Error("a unit name is a run of small letters");
    }
    if (
      typeof exponent !== "number" ||
      !Number.isInteger(exponent) ||
      exponent === 0
    ) {
      throw new Error("an exponent is a whole number that is never zero");
    }
    units.set(name, exponent);
  }
  return units;
}

function readTerm(
  raw: unknown,
): { op: string; count: number; units: Map<string, number> } {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("a term must be a mapping");
  }
  const row = raw as Record<string, unknown>;
  if (typeof row.op !== "string") {
    throw new Error("a term needs an op");
  }
  if (
    typeof row.count !== "number" ||
    !Number.isInteger(row.count)
  ) {
    throw new Error("a count must be a whole number");
  }
  return { op: row.op, count: row.count, units: readUnits(row.units) };
}

function tidy(units: Map<string, number>): Map<string, number> {
  const kept = new Map<string, number>();
  for (const [name, exponent] of units) {
    if (exponent !== 0) {
      kept.set(name, exponent);
    }
  }
  return kept;
}

function alike(one: Map<string, number>, two: Map<string, number>): boolean {
  if (one.size !== two.size) {
    return false;
  }
  for (const [name, exponent] of one) {
    if (two.get(name) !== exponent) {
      return false;
    }
  }
  return true;
}

export function foldDimensionTerms(
  terms: Array<Record<string, unknown>>,
): Record<string, unknown> {
  if (!Array.isArray(terms) || terms.length === 0) {
    throw new Error("there must be at least one term");
  }
  const first = readTerm(terms[0]);
  if (first.op !== "=") {
    throw new Error("the first term must carry the op =");
  }
  let count = first.count === 0 ? 0 : first.count;
  let units = tidy(first.units);

  for (const raw of terms.slice(1)) {
    const term = readTerm(raw);
    if (term.op === "*") {
      count *= term.count;
      const next = new Map(units);
      for (const [name, exponent] of term.units) {
        next.set(name, (next.get(name) ?? 0) + exponent);
      }
      units = tidy(next);
    } else if (term.op === "/") {
      if (term.count === 0) {
        throw new Error("a divisor's count may not be zero");
      }
      if (count % term.count !== 0) {
        throw new Error("that division does not come out whole");
      }
      count = count / term.count;
      const next = new Map(units);
      for (const [name, exponent] of term.units) {
        next.set(name, (next.get(name) ?? 0) - exponent);
      }
      units = tidy(next);
    } else if (term.op === "+" || term.op === "-") {
      if (!alike(units, term.units)) {
        throw new Error("unlike units cannot be added");
      }
      count = term.op === "+" ? count + term.count : count - term.count;
    } else {
      throw new Error("a later op must be one of * / + -");
    }
    count = count === 0 ? 0 : count;
  }

  const shown: Record<string, number> = {};
  for (const [name, exponent] of units) {
    shown[name] = exponent;
  }
  return { count, units: shown };
}
