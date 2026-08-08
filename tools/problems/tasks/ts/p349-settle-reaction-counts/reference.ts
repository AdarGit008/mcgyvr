const SYMBOL = /^[A-Z][a-z]?$/;
const TOP = 10;
const ROOM = 5;

function checkSide(side: unknown, label: string): Record<string, number>[] {
  if (!Array.isArray(side)) {
    throw new Error(`the ${label} side must be a list`);
  }
  if (side.length === 0) {
    throw new Error(`the ${label} side must name at least one species`);
  }
  for (const species of side) {
    if (
      typeof species !== "object" ||
      species === null ||
      Array.isArray(species)
    ) {
      throw new Error("a species must be a plain mapping");
    }
    const keys = Object.keys(species);
    if (keys.length === 0) {
      throw new Error("a species must mention at least one symbol");
    }
    for (const symbol of keys) {
      if (!SYMBOL.test(symbol)) {
        throw new Error("a symbol is one capital letter and at most one small one");
      }
      const held = species[symbol];
      if (typeof held !== "number" || !Number.isInteger(held) || held < 1) {
        throw new Error("a holding must be a whole number of one or more");
      }
    }
  }
  return side;
}

export function settleReactionCounts(
  left: Record<string, number>[],
  right: Record<string, number>[],
): number[] {
  const leftSide = checkSide(left, "left-hand");
  const rightSide = checkSide(right, "right-hand");
  const names = [...leftSide, ...rightSide];
  if (names.length > ROOM) {
    throw new Error("the two sides may name at most five species between them");
  }

  const symbols: string[] = [];
  for (const species of names) {
    for (const symbol of Object.keys(species)) {
      if (!symbols.includes(symbol)) {
        symbols.push(symbol);
      }
    }
  }
  const width = symbols.length;
  const vectors = names.map((species, index) =>
    symbols.map(
      (symbol) =>
        (species[symbol] ?? 0) * (index < leftSide.length ? 1 : -1),
    ),
  );

  const size = names.length;
  const totals = new Array(width).fill(0);
  const choice = new Array(size).fill(0);
  let best: number[] | null = null;
  let bestSum = Number.MAX_SAFE_INTEGER;

  function walk(index: number, sum: number): void {
    if (sum + (size - index) >= bestSum) {
      return;
    }
    if (index === size) {
      if (totals.every((value) => value === 0)) {
        bestSum = sum;
        best = choice.slice();
      }
      return;
    }
    for (let take = 1; take <= TOP; take += 1) {
      choice[index] = take;
      for (let e = 0; e < width; e += 1) {
        totals[e] += vectors[index][e] * take;
      }
      walk(index + 1, sum + take);
      for (let e = 0; e < width; e += 1) {
        totals[e] -= vectors[index][e] * take;
      }
    }
  }

  walk(0, 0);
  return best === null ? [] : best;
}
