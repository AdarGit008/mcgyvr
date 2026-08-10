/** Deployment order of services as waves of a dependency graph. */

function catalogOf(services: [string, string[]][]): Map<string, string[]> {
  const requiresOf = new Map<string, string[]>();
  for (const [name, requires] of services) {
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("service name must be a non-empty string");
    }
    if (requiresOf.has(name)) {
      throw new Error(`duplicate service: ${name}`);
    }
    requiresOf.set(name, requires);
  }
  return requiresOf;
}

function checkEdges(requiresOf: Map<string, string[]>): void {
  for (const [name, requires] of requiresOf) {
    const seen = new Set<string>();
    for (const dep of requires) {
      if (typeof dep !== "string") {
        throw new Error(`non-string dependency on service: ${name}`);
      }
      if (dep === name) {
        throw new Error(`service depends on itself: ${name}`);
      }
      if (!requiresOf.has(dep)) {
        throw new Error(`unknown dependency: ${dep}`);
      }
      if (seen.has(dep)) {
        throw new Error(`dependency listed twice: ${dep}`);
      }
      seen.add(dep);
    }
  }
}

export function deployWaves(services: [string, string[]][]): string[][] {
  const requiresOf = catalogOf(services);
  checkEdges(requiresOf);
  const placed = new Set<string>();
  const waves: string[][] = [];
  while (placed.size < requiresOf.size) {
    const ready: string[] = [];
    for (const [name, requires] of requiresOf) {
      if (placed.has(name)) {
        continue;
      }
      if (requires.every((dep) => placed.has(dep))) {
        ready.push(name);
      }
    }
    if (ready.length === 0) {
      throw new Error("dependency cycle detected");
    }
    ready.sort();
    waves.push(ready);
    for (const name of ready) {
      placed.add(name);
    }
  }
  return waves;
}
