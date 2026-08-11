/** Walks a courier relay directory station by station. */

export function traceRelay(links: Record<string, string>, start: string): string[] {
  for (const [station, target] of Object.entries(links)) {
    if (station === "") {
      throw new Error("station names must be non-empty");
    }
    if (typeof target !== "string") {
      throw new Error("every link must name a station or be empty");
    }
  }
  if (typeof start !== "string" || !(start in links)) {
    throw new Error("unknown starting station");
  }
  const path: string[] = [];
  const visited = new Set<string>();
  let current = start;
  for (;;) {
    if (visited.has(current)) {
      throw new Error("the relay circles back to " + current);
    }
    visited.add(current);
    path.push(current);
    const next = links[current];
    if (next === "") {
      return path;
    }
    if (!(next in links)) {
      throw new Error("a link points at a station the directory does not hold");
    }
    current = next;
  }
}
