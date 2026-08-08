export function walkLadderBoard(
  size: number,
  chutes: number[][],
  pushes: number[],
): number {
  if (typeof size !== "number" || !Number.isInteger(size) || size < 2) {
    throw new Error("size must be a whole number of at least 2");
  }
  if (!Array.isArray(chutes) || !Array.isArray(pushes)) {
    throw new Error("chutes and pushes must be lists");
  }
  const exitOf = new Map<number, number>();
  const mouths = new Set<number>();
  for (const pair of chutes) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("a chute is a [mouth, exit] pair");
    }
    const [mouth, exit] = pair;
    for (const square of [mouth, exit]) {
      if (
        typeof square !== "number" ||
        !Number.isInteger(square) ||
        square < 1 ||
        square > size
      ) {
        throw new Error("a chute square must be a whole number on the track");
      }
    }
    if (mouth === exit) {
      throw new Error("a mouth may not be its own exit");
    }
    if (mouth === 1 || mouth === size) {
      throw new Error("a mouth may not sit on the first or last square");
    }
    if (mouths.has(mouth)) {
      throw new Error("two chutes share one mouth");
    }
    mouths.add(mouth);
    exitOf.set(mouth, exit);
  }
  for (const exit of exitOf.values()) {
    if (mouths.has(exit)) {
      throw new Error("an exit may not be a mouth");
    }
  }
  for (const push of pushes) {
    if (typeof push !== "number" || !Number.isInteger(push) || push < 1) {
      throw new Error("a push must be a whole number above zero");
    }
  }

  let at = 1;
  for (const push of pushes) {
    if (at === size) {
      break;
    }
    const landing = at + push;
    if (landing > size) {
      continue;
    }
    at = exitOf.has(landing) ? (exitOf.get(landing) as number) : landing;
  }
  return at;
}
