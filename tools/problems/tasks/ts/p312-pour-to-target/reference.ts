export function pourToTarget(
  capacities: number[],
  wanted: number,
): string[] | null {
  if (!Array.isArray(capacities) || capacities.length === 0) {
    throw new Error("capacities must be a non-empty list");
  }
  for (const capacity of capacities) {
    if (!Number.isInteger(capacity) || capacity < 1) {
      throw new Error("every capacity must be a whole number of at least one");
    }
  }
  if (!Number.isInteger(wanted) || wanted < 0) {
    throw new Error("wanted must be a whole number of at least zero");
  }

  const count = capacities.length;
  const label = (index: number): string => String.fromCharCode(65 + index);
  const holds = (situation: number[]): boolean =>
    situation.some((amount) => amount === wanted);

  const start = new Array(count).fill(0) as number[];
  if (holds(start)) {
    return [];
  }

  const routes = new Map<string, string[]>();
  routes.set(start.join(","), []);
  let frontier: number[][] = [start];

  while (frontier.length > 0) {
    const nextFrontier: number[][] = [];
    for (const situation of frontier) {
      const route = routes.get(situation.join(","))!;
      const steps: [string, number[]][] = [];
      for (let i = 0; i < count; i++) {
        const after = situation.slice();
        after[i] = capacities[i];
        steps.push([`fill ${label(i)}`, after]);
      }
      for (let i = 0; i < count; i++) {
        const after = situation.slice();
        after[i] = 0;
        steps.push([`empty ${label(i)}`, after]);
      }
      for (let i = 0; i < count; i++) {
        for (let j = 0; j < count; j++) {
          if (i === j) {
            continue;
          }
          const room = capacities[j] - situation[j];
          const moved = Math.min(situation[i], room);
          const after = situation.slice();
          after[i] -= moved;
          after[j] += moved;
          steps.push([`pour ${label(i)} ${label(j)}`, after]);
        }
      }
      for (const [action, after] of steps) {
        const key = after.join(",");
        if (routes.has(key)) {
          continue;
        }
        const extended = route.concat([action]);
        if (holds(after)) {
          return extended;
        }
        routes.set(key, extended);
        nextFrontier.push(after);
      }
    }
    frontier = nextFrontier;
  }
  return null;
}
