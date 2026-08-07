export function raceLadderBoard(
  size: number,
  chutes: number[][],
  turns: (string | number)[][],
): Record<string, number> {
  if (typeof size !== "number" || !Number.isInteger(size) || size < 2) {
    throw new Error("size must be a whole number of at least 2");
  }
  const exitOf = new Map<number, number>();
  for (const pair of chutes) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("a chute is a [mouth, exit] pair");
    }
    const mouth = pair[0];
    const landing = pair[1];
    for (const square of [mouth, landing]) {
      if (
        typeof square !== "number" ||
        !Number.isInteger(square) ||
        square < 1 ||
        square > size
      ) {
        throw new Error("a chute square must be a whole number on the lane");
      }
    }
    if (mouth === landing) {
      throw new Error("a mouth may not be its own exit");
    }
    if (mouth === size) {
      throw new Error("the home square may not be a mouth");
    }
    if (exitOf.has(mouth)) {
      throw new Error("two chutes share one mouth");
    }
    exitOf.set(mouth, landing);
  }
  for (const landing of exitOf.values()) {
    if (exitOf.has(landing)) {
      throw new Error("an exit may not be a mouth");
    }
  }

  const standing = new Map<string, number>();
  for (const turn of turns) {
    if (!Array.isArray(turn) || turn.length !== 2) {
      throw new Error("a turn is a [name, steps] pair");
    }
    const name = turn[0];
    const steps = turn[1];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a runner's name must be a non-empty string");
    }
    if (typeof steps !== "number" || !Number.isInteger(steps) || steps < 1) {
      throw new Error("steps must be a whole number above zero");
    }
    if (!standing.has(name)) {
      standing.set(name, 0);
    }
    const from = standing.get(name) as number;
    if (from === size) {
      continue;
    }
    const arrival = from + steps;
    if (arrival > size) {
      continue;
    }
    const resting = exitOf.has(arrival) ? (exitOf.get(arrival) as number) : arrival;
    for (const other of standing.keys()) {
      if (other !== name && standing.get(other) === resting) {
        standing.set(other, 0);
      }
    }
    standing.set(name, resting);
  }

  const final: Record<string, number> = {};
  for (const name of standing.keys()) {
    final[name] = standing.get(name) as number;
  }
  return final;
}
