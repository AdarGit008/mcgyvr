type Yard = { train: string[]; unrouted: string[] };

function isWholeTrack(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

export function classifyHumpCars(
  cut: Array<[string, string]>,
  table: Record<string, number>,
): Yard {
  if (!Array.isArray(cut)) {
    throw new Error("the cut is a list of cars");
  }
  if (cut.length === 0) {
    throw new Error("the hump has nothing to work");
  }
  if (table === null || typeof table !== "object" || Array.isArray(table)) {
    throw new Error("the routing table is a mapping");
  }
  for (const track of Object.values(table)) {
    if (!isWholeTrack(track)) {
      throw new Error("a track number is a whole number of one or more");
    }
  }

  const numbers = new Set<string>();
  const tracks = new Map<number, string[]>();
  const unrouted: string[] = [];
  for (const entry of cut) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("every car is a pair of a number and a destination");
    }
    const car = entry[0];
    const chalked = entry[1];
    if (
      typeof car !== "string" ||
      car.length === 0 ||
      typeof chalked !== "string" ||
      chalked.length === 0
    ) {
      throw new Error("a car number and a destination are non-empty strings");
    }
    if (numbers.has(car)) {
      throw new Error("two cars carry the number " + car);
    }
    numbers.add(car);
    if (!Object.prototype.hasOwnProperty.call(table, chalked)) {
      unrouted.push(car);
      continue;
    }
    const track = table[chalked];
    const standing = tracks.get(track);
    if (standing === undefined) {
      tracks.set(track, [car]);
    } else {
      standing.push(car);
    }
  }

  const train: string[] = [];
  for (const track of [...tracks.keys()].sort((a, b) => a - b)) {
    for (const car of tracks.get(track)) {
      train.push(car);
    }
  }
  return { train, unrouted };
}
