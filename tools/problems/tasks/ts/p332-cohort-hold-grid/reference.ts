const PERIOD_CEILING = 100000;

function readPair(record: unknown): [string, number] {
  if (!Array.isArray(record) || record.length !== 2) {
    throw new Error("every record must be a pair");
  }
  const key = record[0];
  const period = record[1];
  if (typeof key !== "string" || key.length === 0) {
    throw new Error("a key must be a non-empty string");
  }
  if (!Number.isInteger(period) || period < 0 || period > PERIOD_CEILING) {
    throw new Error("a period must be a whole number from 0 through 100000");
  }
  return [key, period];
}

export function cohortHoldGrid(
  members: Array<[string, number]>,
  sightings: Array<[string, number]>,
  horizon: number,
): number[][] {
  if (!Array.isArray(members)) {
    throw new Error("members must be a list");
  }
  if (!Array.isArray(sightings)) {
    throw new Error("sightings must be a list");
  }
  if (!Number.isInteger(horizon) || horizon < 0 || horizon > 50) {
    throw new Error("horizon must be a whole number from 0 through 50");
  }

  const intake = new Map<string, number>();
  for (const record of members) {
    const [key, period] = readPair(record);
    if (intake.has(key)) {
      throw new Error(`member ${key} is logged twice`);
    }
    intake.set(key, period);
  }

  const alive = new Map<string, Set<number>>();
  for (const record of sightings) {
    const [key, period] = readPair(record);
    const signed = intake.get(key);
    if (signed === undefined) {
      throw new Error(`sighting names unlogged member ${key}`);
    }
    if (period < signed) {
      throw new Error(`sighting for ${key} stands before its intake`);
    }
    let periods = alive.get(key);
    if (periods === undefined) {
      periods = new Set<number>();
      alive.set(key, periods);
    }
    periods.add(period);
  }

  const groups = new Map<number, string[]>();
  for (const [key, period] of intake) {
    const bucket = groups.get(period);
    if (bucket === undefined) {
      groups.set(period, [key]);
    } else {
      bucket.push(key);
    }
  }

  const rows: number[][] = [];
  const intakes = [...groups.keys()].sort((left, right) => left - right);
  for (const period of intakes) {
    const keys = groups.get(period) ?? [];
    const row: number[] = [period, keys.length];
    for (let offset = 0; offset <= horizon; offset++) {
      let tally = 0;
      for (const key of keys) {
        const periods = alive.get(key);
        if (periods !== undefined && periods.has(period + offset)) {
          tally += 1;
        }
      }
      row.push(tally);
    }
    rows.push(row);
  }
  return rows;
}
