/** An installation order for packages under prerequisite pairs. */
export function installOrder(
  packages: string[],
  requires: string[][],
): string[] {
  const known = new Set(packages);
  if (known.size !== packages.length) {
    throw new Error("a package is listed twice");
  }
  const needs: Record<string, number> = {};
  const enables: Record<string, string[]> = {};
  for (const name of packages) {
    needs[name] = 0;
    enables[name] = [];
  }
  for (const [pkg, needed] of requires) {
    if (!known.has(pkg) || !known.has(needed)) {
      throw new Error("a requirement names an unknown package");
    }
    needs[pkg] += 1;
    enables[needed].push(pkg);
  }
  const ready = packages.filter((name) => needs[name] === 0).sort();
  const order: string[] = [];
  while (ready.length > 0) {
    const next = ready.shift() as string;
    order.push(next);
    for (const follower of enables[next]) {
      needs[follower] -= 1;
      if (needs[follower] === 0) {
        ready.push(follower);
      }
    }
    ready.sort();
  }
  if (order.length !== packages.length) {
    throw new Error("the requirements form a cycle");
  }
  return order;
}
