const SPECIES = /^([A-Z][a-z]?\d*)+$/;
const GROUP = /([A-Z][a-z]?)(\d*)/g;
const TOP = 12;
const ROOM = 5;

function readSpecies(species: string): Map<string, number> {
  if (!SPECIES.test(species)) {
    throw new Error("a species must be a run of groups");
  }
  const counts = new Map<string, number>();
  for (const hit of species.matchAll(GROUP)) {
    const digits = hit[2];
    let count = 1;
    if (digits !== "") {
      if (digits[0] === "0") {
        throw new Error("a count may not carry a leading zero");
      }
      count = Number(digits);
      if (count < 2) {
        throw new Error("a count must be two or more");
      }
    }
    counts.set(hit[1], (counts.get(hit[1]) ?? 0) + count);
  }
  return counts;
}

function readSide(side: string): string[] {
  if (side.trim() === "") {
    throw new Error("a side must list at least one species");
  }
  const parts = side.split(" + ");
  const seen = new Set<string>();
  for (const part of parts) {
    if (seen.has(part)) {
      throw new Error("a species may not be listed twice on one side");
    }
    seen.add(part);
  }
  return parts;
}

export function balanceReaction(equation: string): string {
  if (typeof equation !== "string") {
    throw new Error("the reaction must be a string");
  }
  const sides = equation.split(" -> ");
  if (sides.length !== 2) {
    throw new Error("the reaction must carry exactly one arrow");
  }
  const left = readSide(sides[0]);
  const right = readSide(sides[1]);
  const names = [...left, ...right];
  if (names.length > ROOM) {
    throw new Error("a reaction may name at most five species");
  }
  const tables = names.map(readSpecies);

  const symbols: string[] = [];
  for (const table of tables) {
    for (const symbol of table.keys()) {
      if (!symbols.includes(symbol)) {
        symbols.push(symbol);
      }
    }
  }
  const width = symbols.length;
  const vectors = tables.map((table, index) =>
    symbols.map(
      (symbol) => (table.get(symbol) ?? 0) * (index < left.length ? 1 : -1),
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
  if (best === null) {
    return "";
  }
  const picked: number[] = best;
  const render = (from: number, list: string[]): string =>
    list
      .map((name, i) =>
        picked[from + i] === 1 ? name : `${picked[from + i]} ${name}`,
      )
      .join(" + ");
  return `${render(0, left)} -> ${render(left.length, right)}`;
}
