type Standing = {
  name: string;
  total: number;
  best: number;
  counted: number[];
};

function whole(value: unknown, least: number, what: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < least) {
    throw new Error(`${what} must be a whole number of at least ${least}`);
  }
  return value;
}

export function rankSeriesNet(
  entries: Record<string, unknown>[],
  bands: Record<string, number>[],
): Record<string, unknown> {
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("there must be at least one entry");
  }
  if (!Array.isArray(bands) || bands.length === 0) {
    throw new Error("there must be at least one band");
  }

  const table: { limit: number; allowance: number }[] = [];
  let highest = -1;
  for (const band of bands) {
    const limit = whole(band.limit, 0, "a band limit");
    const allowance = whole(band.allowance, 0, "a band allowance");
    if (limit <= highest) {
      throw new Error("the band limits must strictly rise");
    }
    highest = limit;
    table.push({ limit, allowance });
  }

  const names = new Set<string>();
  const standing: Standing[] = [];
  const unranked: string[] = [];

  for (const entry of entries) {
    const name = entry.name;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("every entry needs a name");
    }
    if (names.has(name)) {
      throw new Error(`${name} is entered twice`);
    }
    names.add(name);

    const mark = whole(entry.mark, 0, `the mark of ${name}`);
    const band = table.find((each) => mark <= each.limit);
    if (band === undefined) {
      throw new Error(`the mark of ${name} lies above every band`);
    }
    const base = band.allowance;

    const rounds = entry.rounds;
    if (!Array.isArray(rounds)) {
      throw new Error(`the rounds of ${name} must be a list`);
    }
    const nets: number[] = [];
    for (const round of rounds) {
      const gross = whole(round.gross, 1, `a gross score of ${name}`);
      const weight = whole(round.weight, 1, `a weight of ${name}`);
      if (weight > 200) {
        throw new Error(`a weight of ${name} is above two hundred`);
      }
      nets.push(gross - Math.floor((base * weight) / 100));
    }

    if (nets.length < 3) {
      unranked.push(name);
      continue;
    }

    let counted = nets.map((_, index) => index);
    if (nets.length > 3) {
      let worst = 0;
      for (let index = 1; index < nets.length; index++) {
        if (nets[index] >= nets[worst]) {
          worst = index;
        }
      }
      counted = counted.filter((index) => index !== worst);
    }
    let total = 0;
    let best = nets[counted[0]];
    for (const index of counted) {
      total += nets[index];
      if (nets[index] < best) {
        best = nets[index];
      }
    }
    standing.push({ name, total, best, counted });
  }

  standing.sort((left, right) => {
    if (left.total !== right.total) {
      return left.total - right.total;
    }
    if (left.best !== right.best) {
      return left.best - right.best;
    }
    return left.name < right.name ? -1 : 1;
  });
  unranked.sort();

  return {
    standings: standing.map((row, index) => ({
      place: index + 1,
      name: row.name,
      total: row.total,
      counted: row.counted,
    })),
    unranked,
  };
}
