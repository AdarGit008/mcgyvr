/** Choose the depot a courier should ride to on the city grid. */

export function taxiDistance(a: number[], b: number[]): number {
  return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
}

export function nearestDepot(origin: number[], depots: number[][]): number {
  if (depots.length === 0) {
    throw new Error("at least one depot is needed");
  }
  for (const point of [origin, ...depots]) {
    if (!Number.isInteger(point[0]) || !Number.isInteger(point[1])) {
      throw new Error("coordinates must be integer blocks");
    }
  }
  let best = 0;
  let bestDistance = taxiDistance(origin, depots[0]);
  for (let i = 1; i < depots.length; i++) {
    const distance = taxiDistance(origin, depots[i]);
    if (distance < bestDistance) {
      best = i;
      bestDistance = distance;
    }
  }
  return best;
}
