/** Fewest links to ride between two stations of a transit map. */
export function routeHops(links: string[][], origin: string, goal: string): number {
  const named = (value: unknown): boolean =>
    typeof value === "string" && value.length > 0;
  if (!named(origin) || !named(goal)) {
    throw new Error("station names must be non-empty strings");
  }
  const next = new Map<string, string[]>();
  for (const link of links) {
    if (!Array.isArray(link) || link.length !== 2 || !link.every(named)) {
      throw new Error("a link must join two named stations");
    }
    next.set(link[0], [...(next.get(link[0]) ?? []), link[1]]);
    next.set(link[1], [...(next.get(link[1]) ?? []), link[0]]);
  }
  const seen = new Set<string>([origin]);
  const queue: [string, number][] = [[origin, 0]];
  for (let i = 0; i < queue.length; i++) {
    const [station, hops] = queue[i];
    if (station === goal) return hops;
    for (const neighbour of next.get(station) ?? []) {
      if (!seen.has(neighbour)) {
        seen.add(neighbour);
        queue.push([neighbour, hops + 1]);
      }
    }
  }
  return -1;
}
