export function stepCost(distance: number, rate: number): number {
  return distance * rate;
}

/** The cost of a whole trip, never below the minimum charge. */
export function tripCost(
  hops: number[],
  rate: number,
  minimum: number,
): number {
  let total = 0;
  for (const hop of hops) {
    total += stepCost(hop, rate);
  }
  return Math.max(total, minimum);
}
